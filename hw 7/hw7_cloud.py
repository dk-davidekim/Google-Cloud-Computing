import apache_beam as beam
from apache_beam.io import fileio
import re

BUCKET = 'bu-ds561-dk98-bucket'
DIRECTORY = 'hw2_output'

class ReadFiles(beam.DoFn):
    def process(self, file_metadata):
        file_name = file_metadata.metadata.path
        with file_metadata.open() as file:
            contents = file.read().decode('utf-8')
            yield file_name, contents

def extract(x):
    from bs4 import BeautifulSoup
    file_name, content = x
    bs = BeautifulSoup(content, 'html.parser')
    for a in bs.find_all('a', href=True):
        link = a.get('href')
        if re.match(r'\d+\.html', link):
            file_match = re.search(r'(\d+)(?=.html$)',file_name)
            link_match = re.search(r'(\d+)(?=.html$)',link)
            file_match = file_match.group(1)
            link_match = link_match.group(1)
            yield (file_match, link_match)

def count(x):
    a, b = x
    return a, len(list(b))

def run():
    options = beam.options.pipeline_options.PipelineOptions(
        [
            '--runner=DataflowRunner',
            '--project=ds-561',
            '--temp_location=gs://bu-ds561-dk98-bucket/temp',
            '--region=us-east1',
            '--requirements_file=requirements.txt'
        ]
    )

    with beam.Pipeline(options=options) as p:
        outgoing_links = (
            p 
            | 'MatchFiles' >> fileio.MatchFiles(f'gs://{BUCKET}/{DIRECTORY}/*.html')
            | 'ReadMatches' >> fileio.ReadMatches()
            | 'ReadFiles' >> beam.ParDo(ReadFiles())
            | 'Extract' >> beam.FlatMap(extract)
        )

        incoming_links = (
            outgoing_links
            | 'Swap' >> beam.Map(lambda x: (x[1], x[0]))
        )

        outgoing_count = (
            outgoing_links 
            | 'GroupByOrigin' >> beam.GroupByKey()
            | 'CountOutgoing' >> beam.Map(count)
        )

        incoming_count = (
            incoming_links
            | 'GroupByTarget' >> beam.GroupByKey()
            | 'CountIncoming' >> beam.Map(count)
        )

        top_outgoing = (
            outgoing_count
            | 'Top5Outgoing' >> beam.transforms.combiners.Top.Of(5, key=lambda x: x[1])
        )

        top_incoming = (
            incoming_count
            | 'Top5Incoming' >> beam.transforms.combiners.Top.Of(5, key=lambda x: x[1])
        )

        top_outgoing | 'WriteTopOutgoingResults' >> beam.io.WriteToText(f'gs://{BUCKET}/output/top_outgoing')
        top_incoming | 'WriteTopIncomingResults' >> beam.io.WriteToText(f'gs://{BUCKET}/output/top_incoming')

if __name__ == '__main__':
    run()