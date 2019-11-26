import csv
import logging
from indra.util.aws import get_s3_client

from .processor import PhosphoElmProcessor

logger = logging.getLogger(__name__)

s3_bucket = 'bigmech'
ppelm_s3_key = 'indra-db/external_databases/phosphoELM_all_2015-04.dump'
kinases_list_web = 'http://phospho.elm.eu.org/kinases.html'


def process_from_dump(fname=None, delimiter='\t'):
    """Process a phospho.ELM file dump

    Parameters
    ----------
    fname : str
        File path to the phospho.ELM file dump. If none is provided,
        the file will be downloaded from S3.
    delimiter : str
        The delimiter to use for csv.reader

    Returns
    -------
    indra.sources.phosphoelm.PhosphoElmProcessor
        An instance of a PhosphoElmProcessor containing the statements
        generated from the file dump
    """
    if fname is None:
        s3 = get_s3_client(False)
        s3_obj = s3.get_object(Bucket=s3_bucket, Key=ppelm_s3_key)
        csv_reader = csv.reader(
            s3_obj['Body'].read().decode('utf8').splitlines(True),
            delimiter='\t'
        )
        ppelm_json = _get_json_from_entry_rows(csv_reader)
    else:
        with open(fname, 'r') as f:
            # f.readlines is needed so that the file content is consumed
            # before exiting the with-open clause
            csv_reader = csv.reader(f, delimiter=delimiter)
            ppelm_json = _get_json_from_entry_rows(csv_reader)
    pep = PhosphoElmProcessor(ppelm_json)
    pep.process_phosphorylations()
    return pep


def _get_json_from_entry_rows(row_iter):
    """Loop body to generate a json friendly structure"""
    ppelm_json = []
    columns = next(row_iter)
    for entry in row_iter:
        row_dict = {c: e for c, e in zip(columns, entry)}
        ppelm_json.append(row_dict)
    return ppelm_json
