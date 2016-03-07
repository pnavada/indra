import rdflib
import urllib, urllib2
from functools32 import lru_cache

uniprot_url = 'http://www.uniprot.org/uniprot/'

rdf_prefixes = """
    PREFIX up: <http://purl.uniprot.org/core/>
    PREFIX db: <http://purl.uniprot.org/database/>
    PREFIX faldo: <http://biohackathon.org/resource/faldo#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> """

@lru_cache(maxsize=1000)
def query_protein(protein_id):
    url = uniprot_url + protein_id + '.rdf'
    g = rdflib.Graph()
    try:
        g.parse(url)
    except urllib2.HTTPError:
        print 'Could not find protein with id %s' % protein_id
        return None
    # Check if the entry has been replaced by a new entry
    query = rdf_prefixes + """
        SELECT ?res2
        WHERE {
            ?res1 up:replacedBy ?res2 .
            }
        """
    res = g.query(query)
    if res:
        term = [r for r in res][0][0]
        replaced_by_id = term.split('/')[-1]
        return query_protein(replaced_by_id)
    return g

def get_family_members(family_name, human_only=True):
    data = {'query': 'family:%s' % family_name, 
            'format': 'list'}
    if human_only:
        data['fil'] = 'organism:human'
    req = urllib2.Request(uniprot_url, urllib.urlencode(data))
    res = urllib2.urlopen(req)
    html = res.read()
    if html:
        protein_list = html.strip().split('\n')
        gene_names = []
        for p in protein_list:
            g  = query_protein(p)
            hgnc_name = get_hgnc_name(g)
            gene_names.append(hgnc_name)
        return gene_names
    else:
        return None

def get_hgnc_name(g):
    query = rdf_prefixes + """
        SELECT ?name
        WHERE {
            ?res a up:Resource .
            ?res up:database db:HGNC .
            ?res rdfs:comment ?name .
            }
        """
    res = g.query(query)
    if res:
        hgnc_name = [r for r in res][0][0].toPython()
        return hgnc_name
    else:
        return None


def get_gene_name(g):
    # This is an alternative to get_hgnc_name and is useful when
    # HGNC name is not availabe (for instance, when the organism
    # is not homo sapiens)
    query = rdf_prefixes + """
        SELECT ?name
        WHERE {
            ?gene a up:Gene .
            ?gene skos:prefLabel ?name .
            }
        """
    res = g.query(query)
    if res:
        gene_name = [r for r in res][0][0].toPython()
        return gene_name
    else:
        return None


def get_sequence(g):
    query = rdf_prefixes + """
        SELECT ?seq
        WHERE {
            ?simple_seq a up:Simple_Sequence .
            ?simple_seq rdf:value ?seq .
            }
        """
    res = g.query(query)
    seq = [r for r in res][0][0].toPython()
    return seq


def get_modifications(g):
    query = rdf_prefixes + """
        SELECT ?beg_pos ?comment
        WHERE {
            ?mod_res a up:Modified_Residue_Annotation .
            ?mod_res rdfs:comment ?comment .
            ?mod_res up:range ?range .
            ?range faldo:begin ?beg .
            ?range faldo:end ?end .
            ?beg a faldo:ExactPosition .
            ?beg faldo:position ?beg_pos .
            FILTER (?beg = ?end)
            }
        """
    res = g.query(query)
    mods = []
    for r in res:
        mod_pos = r[0].value
        # "Phosphothreonine; by autocatalysis"
        # "Phosphothreonine; by MAP2K1 and MAP2K2"
        # TODO: take into account the comment after the ;?
        mod_res = r[1].value.split(';')[0]
        mods.append((mod_res, mod_pos))
    return mods


def verify_location(g, residue, location):
    """
    Verify if a given residue is at the given location
    acording to the UniProt sequence
    """
    seq = get_sequence(g)
    try:
        loc_int = int(location)
    except ValueError:
        print 'Invalid location %s' % location
        loc_int = -1

    if (loc_int < 1) or (loc_int > len(seq)):
        return False
    elif seq[loc_int - 1] == residue:
        return True
    return False


def verify_modification(g, residue, location=None):
    """
    Verify if a given residue at the given location
    has a reported modification. If location is not
    given, we only check if there is any residue of the
    given type that is modified.
    """
    mods = get_modifications(g)
    mod_locs = [m[1] for m in mods]
    seq = get_sequence(g)
    if location:
        if not verify_location(g, residue, location):
            return False
        try:
            mod_idx = mod_locs.index(location)
        except ValueError:
            return False
        return True
    else:
        for ml in mod_locs:
            if seq[ml - 1] == residue:
                return True
        return False

if __name__ == '__main__':
    g = query_protein('Q02750')
    seq = get_sequence(g)
    mods = get_modifications(g)
    hgnc_name = get_hgnc_name(g)
    gene_name = get_gene_name(g)
