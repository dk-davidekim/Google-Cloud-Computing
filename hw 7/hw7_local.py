import apache_beam as beam
from apache_beam.io import fileio
from bs4 import BeautifulSoup
import re
import logging

logging.basicConfig(level=logging.INFO, filename='logger.log', filemode='w', format='%(name)s - %(levelname)s - %(message)s')

BUCKET = 'bu-ds561-dk98-bucket'
DIRECTORY = 'hw2_output'

class ReadFiles(beam.DoFn):
    def process(self, file_metadata):
        try:
            file_name = file_metadata.metadata.path
            with file_metadata.open() as file:
                contents = file.read().decode('utf-8')
                yield file_name, contents
        except Exception as e:
            logging.error(f"ReadFiles error: {file_metadata.metadata.path}: {e}")

def extract(x):
    try:
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
    except Exception as e:
        logging.error(f'extract_links error: {e}')

def count(x):
    try:
        a, b = x
        return a, len(list(b))
    except Exception as e:
        logging.error(f'count error: {e}')

def run():
    options = beam.options.pipeline_options.PipelineOptions(
        runner='DirectRunner',
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

        top_outgoing | 'WriteOutgoing' >> beam.io.WriteToText(f'/Users/davidekim/Desktop/DataScience/BU/DS561/ds561-davidekim-U66545284/hw7/outgoing')
        top_incoming | 'WriteIncoming' >> beam.io.WriteToText(f'/Users/davidekim/Desktop/DataScience/BU/DS561/ds561-davidekim-U66545284/hw7/incoming')

if __name__ == '__main__':
    run()
