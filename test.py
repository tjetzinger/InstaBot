#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json

import requests
from instagram_api.InstagramAPI import InstagramAPI

import instaloader
import time, random, re, os, shutil, datetime


def my_download(name, session, profile_pic_only=False, download_videos=True, geotags=False,
        fast_update=False, shorter_output=False, sleep=True, quiet=False, filter_func=None, sleep_min=10, my_profile=None):
    """Download one profile"""
    # pylint:disable=too-many-branches,too-many-locals
    # Get profile main page json
    data = instaloader.get_json(name, session, sleep=sleep)
    # check if profile does exist or name has changed since last download
    # and update name and json data if necessary
    name_updated = instaloader.check_id(name, session, data, quiet=quiet, my_profile=my_profile + '/')
    if name_updated != name:
        name = name_updated
        data = instaloader.get_json(name, session, sleep=sleep)
    # Download profile picture
        instaloader.download_profilepic(name, data["entry_data"]["ProfilePage"][0]["user"]["profile_pic_url"],
            quiet=quiet)
    if sleep:
        time.sleep(1.75 * random.random() + 0.25)
    if profile_pic_only:
        return
    # Catch some errors
    if data["entry_data"]["ProfilePage"][0]["user"]["is_private"]:
        if data["config"]["viewer"] is None:
            raise instaloader.LoginRequiredException("profile %s requires login" % name)
        if not data["entry_data"]["ProfilePage"][0]["user"]["followed_by_viewer"]:
            raise instaloader.PrivateProfileNotFollowedException("Profile %s: private but not followed." % name)
    else:
        if data["config"]["viewer"] is not None:
            instaloader._log("profile %s could also be downloaded anonymously." % name, quiet=quiet)
    if ("nodes" not in data["entry_data"]["ProfilePage"][0]["user"]["media"] or
            len(data["entry_data"]["ProfilePage"][0]["user"]["media"]["nodes"]) == 0) \
                    and not profile_pic_only:
        raise instaloader.ProfileHasNoPicsException("Profile %s: no pics found." % name)
    # Iterate over pictures and download them
    def get_last_id(data):
        if len(data["entry_data"]) == 0 or \
                        len(data["entry_data"]["ProfilePage"][0]["user"]["media"]["nodes"]) == 0:
            return None
        else:
            data = data["entry_data"]["ProfilePage"][0]["user"]["media"]["nodes"]
            return int(data[len(data) - 1]["id"])
    totalcount = data["entry_data"]["ProfilePage"][0]["user"]["media"]["count"]
    count = 1
    while get_last_id(data) is not None:
        for node in data["entry_data"]["ProfilePage"][0]["user"]["media"]["nodes"]:
            instaloader._log("[%3i/%3i] " % (count, totalcount), end="", flush=True, quiet=quiet)
            count += 1
            if filter_func is not None and filter_func(node):
                continue

            path = name if my_profile == None else my_profile + '/' + name
            downloaded = instaloader.download_node(node, session, path,
                                       download_videos=download_videos, geotags=geotags,
                                       sleep=sleep, shorter_output=shorter_output, quiet=quiet, sleep_min=sleep_min)
            if fast_update and not downloaded:
                return
        data = instaloader.get_json(name, session, max_id=get_last_id(data), sleep=sleep)


def my_check_id(profile, session, json_data, quiet=False, my_profile=''):
    """
    Consult locally stored ID of profile with given name, check whether ID matches and whether name
    has changed and return current name of the profile, and store ID of profile.
    """
    profile_exists = len(json_data["entry_data"]) > 0 and "ProfilePage" in json_data["entry_data"]
    is_logged_in = json_data["config"]["viewer"] is not None
    try:
        with open(my_profile + profile + "/id", 'rb') as id_file:
            profile_id = int(id_file.read())
        if (not profile_exists) or \
            (profile_id != int(json_data['entry_data']['ProfilePage'][0]['user']['id'])):
            if is_logged_in:
                newname = instaloader.get_username_by_id(session, profile_id)
                instaloader._log("Profile {0} has changed its name to {1}.".format(profile, newname),
                     quiet=quiet)
                os.rename(my_profile + profile, my_profile + '/' + newname)
                return newname
            if profile_exists:
                raise instaloader.ProfileNotExistsException("Profile {0} does not match the stored "
                                                "unique ID {1}.".format(profile, profile_id))
            raise instaloader.ProfileNotExistsException("Profile {0} does not exist. Please login to "
                                            "update profile name. Unique ID: {1}."
                                            .format(profile, profile_id))
        return profile
    except FileNotFoundError:
        pass
    if profile_exists:
        os.makedirs(my_profile + profile.lower(), exist_ok=True)
        with open(my_profile + profile + "/id", 'w') as text_file:
            profile_id = json_data['entry_data']['ProfilePage'][0]['user']['id']
            text_file.write(profile_id+"\n")
            instaloader._log("Stored ID {0} for profile {1}.".format(profile_id, profile), quiet=quiet)
        return profile
    raise instaloader.ProfileNotExistsException("Profile {0} does not exist.".format(profile))


def my_download_node(node, session, name, download_videos=True, geotags=False, sleep=True, shorter_output=False, quiet=False, sleep_min=10):
    """
    Download everything associated with one instagram node, i.e. picture, caption and video.

    :param node: Node, as from media->nodes list in instagram's JSONs
    :param session: Session
    :param name: Name of profile to which this node belongs
    :param download_videos: True, if videos should be downloaded
    :param sleep: Sleep between requests to instagram server
    :param shorter_output: Shorten log output by not printing captions
    :param quiet: Suppress output
    :return: True if something was downloaded, False otherwise, i.e. file was already there
    """
    try:
        filename = instaloader.download_pic(name, node["display_src"], node["date"], quiet=quiet)
        if sleep:
            time.sleep(1.75 * random.random() + 0.25)
        if "caption" in node:
            instaloader.save_caption(name, node["date"], node["caption"], shorter_output, quiet)
        else:
            instaloader._log("<no caption>", end=' ', flush=True, quiet=quiet)
        if node["is_video"] and download_videos:
            video_data = instaloader.get_json('p/' + node["code"], session, sleep=sleep)
            video = instaloader.download_pic(name,
                         video_data['entry_data']['PostPage'][0]['media']['video_url'],
                         node["date"], 'mp4', quiet=quiet)
            InstagramAPI.uploadVideo(video=video, thumbnail=filename, caption=node["caption"])
        else:
            InstagramAPI.uploadPhoto(photo=filename, caption=node["caption"])

        if geotags:
            location = instaloader.get_location(node, session, sleep)
            if location:
                instaloader.save_location(name, location, node["date"])
        instaloader._log(quiet=quiet)

        if sleep:
            time.sleep(sleep_min * 60)
    except instaloader.InstaloaderException as ex:
        print(ex)
        return False

    return True


def my_download_pic(name, url, date_epoch, outputlabel=None, quiet=False):
    """Downloads and saves picture with given url under given directory with given timestamp.
    Returns true, if file was actually downloaded, i.e. updated."""
    if outputlabel is None:
        outputlabel = instaloader._epoch_to_string(date_epoch)
    urlmatch = re.search('\\.[a-z]*\\?', url)
    file_extension = url[-3:] if urlmatch is None else urlmatch.group(0)[1:-1]
    filename = name.lower() + '/' + instaloader._epoch_to_string(date_epoch) + '.' + file_extension
    if os.path.isfile(filename):
        instaloader._log(outputlabel + ' exists', end=' ', flush=True, quiet=quiet)
        raise PicAlreadyDownloadedException("File \'" + filename + "\' already exists.")
    resp = instaloader.get_anonymous_session().get(url, stream=True)
    if resp.status_code == 200:
        instaloader._log(outputlabel, end=' ', flush=True, quiet=quiet)
        os.makedirs(name.lower(), exist_ok=True)
        with open(filename, 'wb') as file:
            resp.raw.decode_content = True
            shutil.copyfileobj(resp.raw, file)
        os.utime(filename, (datetime.datetime.now().timestamp(), date_epoch))
        return filename
    else:
        raise instaloader.ConnectionException("File \'" + url + "\' could not be downloaded.")


instaloader.download = my_download
instaloader.check_id = my_check_id
instaloader.download_node = my_download_node
instaloader.download_pic = my_download_pic


class PicAlreadyDownloadedException(instaloader.NonfatalException):
    pass


class MyInstagramAPI(InstagramAPI):
    def login(self, force=False, proxies=None):
        if (not self.isLoggedIn or force):
            self.s = requests.Session()
            # if you need proxy make something like this:
            self.s.proxies = proxies
            if (self.SendRequest('si/fetch_headers/?challenge_type=signup&guid=' + self.generateUUID(False), None, True)):

                data = {'phone_id'   : self.generateUUID(True),
                        '_csrftoken' : self.LastResponse.cookies['csrftoken'],
                        'username'   : self.username,
                        'guid'       : self.uuid,
                        'device_id'  : self.device_id,
                        'password'   : self.password,
                        'login_attempt_count' : '0'}

                if self.SendRequest('accounts/login/', self.generateSignature(json.dumps(data)), True):
                    self.isLoggedIn = True
                    self.username_id = self.LastJson["logged_in_user"]["pk"]
                    self.rank_token = "%s_%s" % (self.username_id, self.uuid)
                    self.token = self.LastResponse.cookies["csrftoken"]

                    self.syncFeatures()
                    self.autoCompleteUserList()
                    self.timelineFeed()
                    self.getv2Inbox()
                    self.getRecentActivity()
                    print ("Login success!\n")
                    return True

with open('config.json', 'r') as f:
    config = json.load(f)
profile=0

InstagramAPI = MyInstagramAPI(config[profile]['username'], config[profile]['password'])
InstagramAPI.login(proxies=config[profile]['proxies'])  # login
session = instaloader.get_anonymous_session()
for c in config[profile]['channels']:
    instaloader.download(name=c['name'], my_profile=config[profile]['username'], sleep_min=config[profile]['sleep'], session=session, fast_update=False, filter_func=lambda node: node["likes"]["count"] < c['min_likes'])
InstagramAPI.logout()
