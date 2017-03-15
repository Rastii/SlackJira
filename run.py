import argparse
import sys
import logging
import logging.config

from slack_jira import resources

import slackbot.settings
import slackbot.bot


def get_argparser_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--config", dest="config", default="config.ini", metavar="PATH",
        help="Specify configuration file",
    )
    # TODO Add daemon option :-)
    return parser.parse_args()


def do_run(args):
    args = get_argparser_args(args)
    config_file = args.config
    logging.config.fileConfig(config_file)
    logger = logging.getLogger(__name__)

    logger.info("Loading configurations")
    config = resources.load_config_from_path(config_file)
    slackbot_config = resources.SlackBotConfig.from_config(config)

    # Since we can't inject the settings into the bot, let's load all the settings
    # into the module
    slackbot_config.load_into_settings_module(slackbot.settings)
    # Load the config into the settings...
    slackbot.settings.SLACK_JIRA_CONF = config

    logger.info("Starting slackbot")
    bot = slackbot.bot.Bot()
    bot.run()


if __name__ == "__main__":
    sys.exit(do_run(sys.argv))
