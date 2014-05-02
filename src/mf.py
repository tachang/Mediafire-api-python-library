import ConfigParser
import hashlib
import logging
import argparse
import pprint
import os, os.path
from mediafire import MediaFireLib
from retry import retry
import urllib2
from os.path import expanduser

logging.basicConfig(level=logging.DEBUG)

log = logging.getLogger(__name__)

config = ConfigParser.ConfigParser()
configFile = os.path.join(os.path.expanduser("~"),".mediafire/config")
config.readfp(open(configFile))

email = config.get("Settings","email")
password = config.get("Settings","password")
applicationid = config.get("Settings","applicationid")
apikey = config.get("Settings","apikey")

mf = MediaFireLib(_userMail = email, _userPassword = password, _appID = applicationid, _apiKey = apikey)
mf.user_getSessionToken()

def sha256sum(filename):
    sha256 = hashlib.sha256()
    with open(filename,'rb') as f: 
        for chunk in iter(lambda: f.read(128*sha256.block_size), b''): 
            sha256.update(chunk)
    return sha256.hexdigest()

@retry(urllib2.URLError, tries=3)
def get_or_create_folder(folder_path):
  mf.user_getSessionToken()

  if not folder_path.startswith('/'):
    raise Exception("Folder path should start with /") 

  if folder_path == '/':
    # Root folder does not have a folder_key. Return empty string.
    return ''

  folder_pieces = folder_path.strip('/').split('/')

  folder_key = ""
  for piece in folder_pieces:
    result = mf.folder_getContent(folder_key = folder_key, content_type='folders')

    # Check if piece is in folders
    new_folder_key = None
    for folder in result['folder_content']['folders']:
      if folder['name'] == piece:
        new_folder_key = folder['folderkey']

    # If the folder already exists set the folder_key to the one found and continue deeper
    if new_folder_key:
      folder_key = new_folder_key
    else:
      log.debug("Creating folder %s under parentkey %s" % (piece, folder_key))
      result = mf.folder_create(piece, parentKey = folder_key)
      folder_key = result['folderkey']

  return folder_key


def upload(args):

  if args.destination.endswith('/'):
    args.destination = args.destination.rstrip('/')

  # The upload command lets the user specify multiple files or directories
  for upload_file in args.files:

    # If the upload_file is a directory then recurse through all the files and upload them
    if os.path.isdir(upload_file):

      for root, _, files in os.walk(upload_file):
        for f in files:
          full_path = os.path.join(root, f)
          partial_path = os.path.join(root, f)[len(upload_file):] 

          destination_path = args.destination + partial_path
          destination_folder_path = os.path.dirname(destination_path)

          folder_key = get_or_create_folder(destination_folder_path)

          basename = os.path.basename(full_path)
 
          should_upload = True

          if args.dryrun:
            should_upload = False

          # Check to see if the folder contains the file already
          result = mf.folder_getContent(folder_key = folder_key, content_type='files')

          files_uploaded = filter(lambda x: x['filename'] == basename, result['folder_content']['files'])

          if len(files_uploaded) > 0:

            uploaded_file = files_uploaded[0]
            if uploaded_file['hash'] == sha256sum(full_path):
              should_upload = False
              log.info("Skipping file %s" % basename)

          if should_upload:
            log.info("Uploading file %s" % basename)
            mf.upload_UploadFile(full_path, folderKey = folder_key)

    # If the upload_file is a file object
    if os.path.isfile(upload_file):
      pass



# create the top-level parser
parser = argparse.ArgumentParser(description='Mediafire commandline tools')
subparsers = parser.add_subparsers()

parser.add_argument('--dryrun', action='store_true', help="Do a dry run without changing anything.")

upload_parser = subparsers.add_parser('upload')
upload_parser.add_argument('upload', action='store_true', help='Upload a file or directory')
upload_parser.add_argument('files', nargs='*')
upload_parser.add_argument('destination')
upload_parser.set_defaults(func=upload)

# parse the args and call whatever function was selected
args = parser.parse_args()
args.func(args)
