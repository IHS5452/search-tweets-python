#!/usr/bin/env python
# Copyright 2021 Twitter, Inc.
# Licensed under the Apache License, Version 2.0
# http://www.apache.org/licenses/LICENSE-2.0
import os
import argparse
import json
import sys
import logging
import csv
import json
from pathlib import Path

from searchtweets import (ResultStream,
                          load_credentials,
                          merge_dicts,
                          read_config,
                          write_result_stream,
                          gen_params_from_config)

logger = logging.getLogger()
# we want to leave this here and have it command-line configurable via the
# --debug flag
logging.basicConfig(level=os.environ.get("LOGLEVEL", "ERROR"))


REQUIRED_KEYS = {"pt_rule", "endpoint"}


def parse_cmd_args():
    argparser = argparse.ArgumentParser()
    help_msg = """configuration file with all parameters. Far,
          easier to use than the command-line args version.,
          If a valid file is found, all args will be populated,
          from there. Remaining command-line args,
          will overrule args found in the config,
          file."""

    argparser.add_argument("--credential-file",
                           dest="credential_file",
                           default=None,
                           help=("Location of the yaml file used to hold "
                                 "your credentials."))

    argparser.add_argument("--credential-file-key",
                           dest="credential_yaml_key",
                           default=None,
                           help=("the key in the credential file used "
                                 "for this session's credentials. "
                                 "Defaults to search_tweets_api"))

    argparser.add_argument("--env-overwrite",
                           dest="env_overwrite",
                           default=True,
                           help=("""Overwrite YAML-parsed credentials with
                                 any set environment variables. See API docs or
                                 readme for details."""))

    argparser.add_argument("--config-file",
                           dest="config_filename",
                           default=None,
                           help=help_msg)

    argparser.add_argument("--account-type",
                           dest="account_type",
                           default=None,
                           choices=["premium", "enterprise"],
                           help="The account type you are using")

    argparser.add_argument("--count-bucket",
                           dest="count_bucket",
                           default=None,
                           help=("""Set this to make a 'counts' request. Bucket size for counts API. Options:,
                                 day, hour, minute."""))

    argparser.add_argument("--start-datetime",
                           dest="from_date",
                           default=None,
                           help="""Start of datetime window, format
                                'YYYY-mm-DDTHH:MM' (default: -30 days)""")

    argparser.add_argument("--end-datetime",
                           dest="to_date",
                           default=None,
                           help="""End of datetime window, format
                                 'YYYY-mm-DDTHH:MM' (default: most recent
                                 date)""")

    argparser.add_argument("--filter-rule",
                           dest="pt_rule",
                           default=None,
                           help="PowerTrack filter rule (See: https://developer.twitter.com/en/docs/twitter-api/enterprise/search-api/guides/operators)")

    argparser.add_argument("--results-per-call",
                           dest="results_per_call",
                           help="Number of results to return per call "
                                "(default 100; max 500) - corresponds to "
                                "'maxResults' in the API. If making a 'counts' request with '--count-bucket, this parameter is ignored.")

    argparser.add_argument("--max-results", dest="max_results",
                           type=int,
                           help="Maximum number of Tweets or Counts to return for this session")

    argparser.add_argument("--max-pages",
                           dest="max_pages",
                           type=int,
                           default=None,
                           help="Maximum number of pages/API calls to "
                           "use for this session.")

    argparser.add_argument("--results-per-file", dest="results_per_file",
                           default=None,
                           type=int,
                           help="Maximum tweets to save per file.")

    argparser.add_argument("--filename-prefix",
                           dest="filename_prefix",
                           default=None,
                           help="prefix for the filename where tweet "
                           " json data will be stored.")

    argparser.add_argument("--no-print-stream",
                           dest="print_stream",
                           action="store_false",
                           help="disable print streaming")

    argparser.add_argument("--print-stream",
                           dest="print_stream",
                           action="store_true",
                           default=True,
                           help="Print tweet stream to stdout")

    argparser.add_argument("--extra-headers",
                           dest="extra_headers",
                           type=str,
                           default=None,
                           help="JSON-formatted str representing a dict of additional request headers")

    argparser.add_argument("--debug",
                           dest="debug",
                           action="store_true",
                           default=False,
                           help="print all info and warning messages")
    
    argparser.add_argument("--export",
                           choices=["csv","json","both"],
                           default=None,
                           help="Exports tweets to csv, json, or both formats")
    
    
    argparser.add_argument("--filename",
                           dest="output_filename",
                           default="tweets_output",
                           help="Base name for exported CSV/JSON files (Please do not put an extension)")


    return argparser


def _filter_sensitive_args(dict_):
    sens_args = ("password", "consumer_key", "consumer_secret", "bearer_token")
    return {k: v for k, v in dict_.items() if k not in sens_args}




def save_to_csv(tweets, filename="tweets_output.csv"):
    if not tweets:
        print("No tweets to save.")
        return

    keys = tweets[0].keys()
    with open(filename, "w", newline='', encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=keys)
        writer.writeheader()
        writer.writerows(tweets)
    print(f"Saved {len(tweets)} tweets to {filename}")

def save_to_json(tweets, filename="tweets_output.json"):
    if not tweets:
        print("No tweets to save.")
        return

    with open(filename, "w", encoding="utf-8") as jsonfile:
        json.dump(tweets, jsonfile, ensure_ascii=False, indent=2)
    print(f"Saved {len(tweets)} tweets to {filename}")



def main():
    args_dict = vars(parse_cmd_args().parse_args())
    if args_dict.get("debug") is True:
        logger.setLevel(logging.DEBUG)
        logger.debug("command line args dict:")
        logger.debug(json.dumps(args_dict, indent=4))

    
    if args_dict.get("config_filename") is not None:
        configfile_dict = read_config(args_dict["config_filename"])
    else:
        configfile_dict = {}
    
    extra_headers_str = args_dict.get("extra_headers")
    if extra_headers_str is not None:
        args_dict['extra_headers_dict'] = json.loads(extra_headers_str)
        del args_dict['extra_headers']

    logger.debug("config file ({}) arguments sans sensitive args:".format(args_dict["config_filename"]))
    logger.debug(json.dumps(_filter_sensitive_args(configfile_dict), indent=4))

    creds_dict = load_credentials(filename=args_dict["credential_file"],
                                  account_type=args_dict["account_type"],
                                  yaml_key=args_dict["credential_yaml_key"],
                                  env_overwrite=args_dict["env_overwrite"])

    dict_filter = lambda x: {k: v for k, v in x.items() if v is not None}

    config_dict = merge_dicts(dict_filter(configfile_dict),
                              dict_filter(creds_dict),
                              dict_filter(args_dict))

    logger.debug("combined dict (cli, config, creds) sans password:")
    logger.debug(json.dumps(_filter_sensitive_args(config_dict), indent=4))

    if len(dict_filter(config_dict).keys() & REQUIRED_KEYS) < len(REQUIRED_KEYS):
        print(REQUIRED_KEYS - dict_filter(config_dict).keys())
        logger.error("ERROR: not enough arguments for the program to work")
        sys.exit(1)

    stream_params = gen_params_from_config(config_dict)
    logger.debug("full arguments passed to the ResultStream object sans password")
    logger.debug(json.dumps(_filter_sensitive_args(stream_params), indent=4))

    rs = ResultStream(tweetify=False, **stream_params)

    logger.debug(str(rs))

    if config_dict.get("filename_prefix") is not None:
        stream = write_result_stream(rs,
                                     filename_prefix=config_dict.get("filename_prefix"),
                                     results_per_file=config_dict.get("results_per_file"))
    else:
        stream = rs.stream()

    if config_dict["print_stream"]:
        for tweet in stream:
            print(json.dumps(tweet))



    all_tweets = []

    if config_dict["print_stream"]:
        for tweet in stream:
            print(json.dumps(tweet))
            all_tweets.append(tweet)

    export_type = config_dict.get("export")
    output_base = config_dict.get("output_filename", "tweets_output")

    if export_type and all_tweets:
        if export_type in ("csv", "both"):
            save_to_csv(all_tweets, f"{output_base}.csv")
        if export_type in ("json", "both"):
            save_to_json(all_tweets, f"{output_base}.json")

if __name__ == '__main__':
    main()
