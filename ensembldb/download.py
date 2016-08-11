import os
import sys
import warnings
import subprocess
from pprint import pprint
import configparser
from pkg_resources import resource_filename

import click

os.environ['DONT_USE_MPI'] = "1"
from cogent3.util import parallel

from ensembldb.species import Species
from ensembldb.name import EnsemblDbName
from .util import exec_command, abspath, makedirs

__author__ = "Gavin Huttley"
__copyright__ = "Copyright 2016-, The EnsemblDb Project"
__credits__ = ["Gavin Huttley"]
__license__ = "BSD"
__version__ = "3.0a1"
__maintainer__ = "Gavin Huttley"
__email__ = "Gavin.Huttley@anu.edu.au"
__status__ = "alpha"


_remote_pub = "rsync://ftp.ensembl.org/ensembl/pub/"

def rsync_listdir(dirname="", debug=True):
    if dirname:
        cmnd = "%s%s" % (_remote_pub, dirname)
    else:
        cmnd = _remote_pub
    
    cmnd = r"rsync --list-only %s" % cmnd
    if debug:
        print(cmnd)
    result = exec_command(cmnd)
    r = result.splitlines()
    return r

def reduce_dirnames(dirnames, species_dbs, verbose=False, debug=False):
    """returns EnsemblNames corresponding to species db's"""
    if debug:
        pprint(dirnames)
    
    db_names = []
    for record in dirnames:
        record = record.strip()
        if not record:
            continue
        
        record = record.split()[-1]
        if not record[0].isalpha():
            continue
        
        try:
            name = EnsemblDbName(record)
        except (TypeError, RuntimeError):
            # a non-species
            if debug:
                print(record)
            continue
        
        if name.species in species_dbs:
            if name.type not in species_dbs[name.species] and\
               species_dbs[name.species]:
                if debug or verbose:
                    print("Skipping", name)
                continue

            db_names.append(name)
        elif name.type == 'compara' and 'compara' in species_dbs:
            db_names.append(name)
    return db_names

def download_db(remote_path, local_path, verbose=False, debug=False):
    """downloads a db from remote_path to local_path
    
    Parameters
    ----------
    remote_path : str
       The Ensembl ftp path for the db
    
    local_path : str
       local path to write to the data to
    """
    cmnd = "rsync --progress -av %s%s %s" % (_remote_pub, remote_path, local_path)
    if debug or verbose:
        print(cmnd)
        kwargs = dict(stderr=None, stdout=None)
    else:
        kwargs = {}
    
    r = exec_command(cmnd, **kwargs)
    if debug or verbose and r:
        print(r)
    
def read_config(config_path, verbose=False):
    """returns ensembl release, local path, and db specifics from the provided config path"""
    parser = configparser.ConfigParser()
    parser.read_file(config_path)
    release = parser.get('release', 'release')
    local_path = parser.get('local path', 'path')
    local_path = abspath(local_path)
    species_dbs = {}
    for section in parser.sections():
        if section in ('release', 'local path'):
            continue
        
        if section != 'compara':
            species = Species.get_species_name(section, level='raise')
        else:
            species = "compara"
        dbs = [db.strip() for db in parser.get(section, 'db').split(',')]
        species_dbs[species] = dbs
    
    if verbose:
        print("DOWNLOADING\nensembl release=%s\noutput path=%s\n" % (release, local_path))
        pprint(species_dbs)
    return release, local_path, species_dbs

_cfg = os.path.join(ENSEMBLDBRC, 'ensembldb_download.cfg')

def WrapDownload(remote_template, local_base, release, verbose, debug):
    """returns a callback function, that takes the database name and rsync downloads"""
    def rsync_call_wrapper(dbname):
        props = {'dbname': dbname, 'release': release}
        remote_db_path = remote_template % props
        local_db_path = os.path.join(local_base, dbname)
        run_args = dict(remote_path=remote_db_path, local_path=local_db_path,
                        verbose=verbose, debug=debug)
        download_db(**run_args)
    
    return rsync_call_wrapper

def download_dbs(configpath, numprocs, verbose, debug):
    if configpath.name == _cfg:
        warnings.warn("WARN: using the built in demo cfg, will write to /tmp")
    
    release, local_path, sp_db = read_config(configpath, verbose=verbose)
    makedirs(local_path)
    
    props = dict(release=release)
    contents = rsync_listdir('release-%(release)s/mysql/' % props, debug=debug)
    db_names = reduce_dirnames(contents, sp_db, verbose=verbose, debug=debug)
    if verbose or debug:
        pprint(db_names)
    
    if numprocs > 1:
        numprocs = min(numprocs, len(db_names), 5)
        # should print warning if ask for more than 5
        parallel.use_multiprocessing(numprocs)
    
    remote_template = 'release-%(release)s/mysql/%(dbname)s/'
    rsync = WrapDownload(remote_template, local_path, release, verbose=verbose,
                         debug=debug)
    dbnames = [n.name for n in db_names]
    for r in parallel.imap(rsync, dbnames):
        pass

