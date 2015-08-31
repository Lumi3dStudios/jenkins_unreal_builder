"""

        UE4 Project Build File for Jenkins

        Call this script from Jenkins with the build number as the first argument

        The build name will be project_name_year_month_day_hour_minutes_bBUILDNUMBER_cCHANGELISTNUMBER


        Tested with Unreal 4.8

        Author - Luiz Kruel - Lumi 3d Studios - www.lumi3dstudios.com

        Note: The script assumes you're logged into P4. You should login using Jenkins prior to launching this python file

"""

import sys
import os
import boto.ses
import subprocess
import inspect
import datetime
import tinys3

from contextlib import closing
from zipfile import ZipFile, ZIP_DEFLATED
import os

current_file = inspect.getfile(inspect.currentframe())
current_dir = os.path.dirname(current_file)

# You're going to want to change these variables to paths to things that make sense to you

P4_ROOT_PATH = os.path.join(current_dir, "../..")
PROJECT_PATH = "PATH_TO_YOURPROJECT.uproject"
PROJECT_NAME = "my_project"

S3_ACCESS_KEY = "AMAZON_ACCESS_KEY"
S3_SECRET_KEY = "AMAZON_SECRET_KEY"
S3_BUCKET = "your_bucket"
S3_REGION = 'us-west-2'

EMAIL_SENDER = 'build_server@yourstudio.com'
EMAIL_RECEIVER = 'mailing_list@yourstudio.com'

UNREAL_PATH = "C:/Program Files/Unreal Engine/4.8"

def zipdir(basedir, archivename):
    assert os.path.isdir(basedir)
    with closing(ZipFile(archivename, "w", ZIP_DEFLATED)) as z:
        for root, dirs, files in os.walk(basedir):
            #NOTE: ignore empty directories
            for fn in files:
                absfn = os.path.join(root, fn)
                zfn = absfn[len(basedir)+len(os.sep):] #XXX: relative path
                z.write(absfn, zfn)


def build(args):

    # THE %BUILD_NUMBER% variable is expected comming into the script in order to build the name up
    BUILD_NUMBER = args[1]

    # Grab the current time to build the build name
    now = datetime.datetime.now()
    BUILD_TIME = now.strftime("%Y_%m_%d_%H_%M")

    # check what is the last submitted changelist
    output = subprocess.check_output("p4 changes -m 1", cwd = P4_ROOT_PATH )
    last_changelist = output.split()[1]

    builds_dir = os.path.join(P4_ROOT_PATH, "builds/")
    existing_builds = os.listdir(builds_dir)
    for build in existing_builds:
        if os.path.isdir(os.path.join(builds_dir, build)):
            change_number = build.split("_c")[1]
            if change_number == last_changelist:
                print "LATEST BUILD ALREADY EXISTS !!!"
                send_mail('There were no new changes today, build skipped')

                return

    print "Grabbing Latest From Perforce"
    subprocess.check_output("p4 sync", cwd = P4_ROOT_PATH)

    # CHANGE THIS TO CHANGE THE NAME OF THE BUILD
    BUILD_NAME = BUILD_TIME + "_b" + str(BUILD_NUMBER) + "_c" + last_changelist

    output_build_directory = os.path.join(P4_ROOT_PATH, "builds", BUILD_NAME )

    print "Building Unreal Project: " + PROJECT_PATH
    UE4_CMD = UNREAL_PATH + '"/Engine/Build/BatchFiles/RunUAT.bat" BuildCookRun -project=' + PROJECT_PATH + ' -noP4 -platform=Win64 -clientconfig=Development -serverconfig=Development -cook -allmaps-build -stage -pak -archive -archivedirectory="' + output_build_directory + '" -rocket -nokill -cmdline= -addcmdline='
    ue_output = subprocess.check_output(UE4_CMD)
    print ue_output

    print "Zipping up Build"
    zipdir(output_build_directory, output_build_directory + ".zip")

    error = None
    try:
        # Creating a simple connection
        conn = tinys3.Connection(S3_ACCESS_KEY,S3_SECRET_KEY, endpoint='s3-'+ S3_REGION + '.amazonaws.com')
        f = open(output_build_directory + ".zip",'rb')

        print "UPLOADING BUILD TO S3"

        upload_build_path = "%s/%s_%s.zip"%(PROJECT_NAME, PROJECT_NAME, BUILD_NAME)

        conn.upload( upload_build_path, f, S3_BUCKET)
        conn.update_metadata(upload_build_path,{ 'x-amz-storage-class': 'REDUCED_REDUNDANCY'}, S3_BUCKET)

    except:
        error = "Failed to upload"
        
    if error:
        send_mail(error)
    else:
        send_mail('Build is done and uploaded to Amazon. \n You can download it at https://' + S3_BUCKET + '.s3-' + S3_REGION + '.amazonaws.com/' + upload_build_path)

def send_mail(message):

    conn = boto.ses.connect_to_region(
            S3_REGION,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY)

    conn.send_email(
            EMAIL_SENDER,
            'Build Finished',
            message,
            [EMAIL_RECEIVER])

if __name__ == '__main__':
    build(sys.argv)
