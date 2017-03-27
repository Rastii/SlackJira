import argparse
import logging
import logging.config
import sys
import ConfigParser

from slack_jira import resources

import slackbot.settings
import slackbot.bot


class ConfigAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        file_location = values if values else self.default

        config = ConfigParser.ConfigParser()
        try:
            with open(file_location) as fp:
                config.readfp(fp)
        except (IOError, ConfigParser.Error) as e:
            raise argparse.ArgumentError(self, "Unable to read URL file: {}".format(e))

        setattr(namespace, self.dest, config)


def _logging_config(config_parser, disable_existing_loggers=False):
    """
    Helper that allows us to use an existing ConfigParser object to load logging
    configurations instead of a filename.

    Note: this code is essentially copy pasta from `logging.config.fileConfig` except
    we skip loading the file.
    """
    formatters = logging.config._create_formatters(config_parser)

    # critical section
    logging._acquireLock()
    try:
        logging._handlers.clear()
        del logging._handlerList[:]
        # Handlers add themselves to logging._handlers
        handlers = logging.config._install_handlers(config_parser, formatters)
        logging.config._install_loggers(config_parser, handlers, disable_existing_loggers)
    finally:
        logging._releaseLock()


def get_parser_args(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--config", dest="config", default="config.ini",
        metavar="PATH", action=ConfigAction,
        help="Specify configuration file",
    )
    # TODO: Perhaps we will make a daemon
    return parser.parse_args(args=args)


def main(args=None):
    args = get_parser_args(args)
    _logging_config(args.config)
    logger = logging.getLogger(__name__)

    logger.info("Loading configurations")
    slackbot_config = resources.SlackBotConfig.from_config(args.config)

    # Since we can't inject the settings into the bot, let's load all the settings
    # into the module
    slackbot_config.load_into_settings_module(slackbot.settings)
    # Load the config into the settings...
    # TODO: PR to be able to inject settings instead of auto magically loading them from a module
    slackbot.settings.SLACK_JIRA_CONF = args.config

    logger.info("Starting slackbot")
    bot = slackbot.bot.Bot()
    bot.run()


if __name__ == "__main__":
    sys.exit(main())
