import ConfigParser
import functools
import logging
import collections
import re

import jira


logger = logging.getLogger(__name__)


class Error(Exception):
    """
    Module level error
    """


class ConfigError(Error):
    """
    There was an error loading/parsing the configuration
    """


class JiraError(Error):
    """
    There was an issue instantiating the JIRA object.
    """


def get_config_value(config_parser, section, option, required=True, get_type=str, default=None):
    """
    Retrieves a config value from a config parser.

    :type config_parser: ConfigParser.ConfigParser
    :param config_parser: The config parser object instance to extract values from
    :type section: str
    :param section: The section to extract values from
    :type option: str
    :param option: The option to extract a value from
    :type required: bool
    :param required: If set to true and an option is missing, an error will be raised.
        Otherwise, None will be returned.
    :param get_type: Specify the config parser type, either int|bool|str

    :rtype: str
    :return: The value extracted from the ConfigParser object

    :raises ConfigError: When the ConfigParser did not contain the specified value
        based on the section and option
    """
    if get_type is int:
        getter = config_parser.getint
    elif get_type is bool:
        getter = config_parser.getboolean
    else:
        getter = config_parser.get

    try:
        value = getter(section, option)
    except ConfigParser.Error:
        if required:
            raise ConfigError("Missing configuration '{}' in section '{}'".format(option, section))
        return default

    return value


__ISSUE_SUMMARY_FIELDS = [
    "issue",
    "title",
    "status",
    "priority",
    "description",
    "link",
    "assignee",
    "original_estimate",
    "remaining_estimate",
]


class JiraIssueSummary(collections.namedtuple("JiraIssueSummary", __ISSUE_SUMMARY_FIELDS)):
    """
    Named tuple that contains a summary of a Jira issue.
    """
    __slots__ = ()


__JIRA_MSG_HANDLER_CONFIG_FIELDS = [
    "max_issues",
    "response_threshold",
    "ticket_cache_size",
    "full_attachments",
]


class JiraMsgHandlerConfig(collections.namedtuple("JiraMsgHandlerConfig",
                                                  __JIRA_MSG_HANDLER_CONFIG_FIELDS)):
    __slots__ = ()

    @staticmethod
    def from_config(conf, section="jira_message_handler"):
        get_value = functools.partial(get_config_value, conf, section, required=False)
        return JiraMsgHandlerConfig(
            max_issues=get_value("max_issues", get_type=int),
            response_threshold=get_value("response_threshold", get_type=int),
            ticket_cache_size=get_value("ticket_cache_size", get_type=int),
            full_attachments=get_value("full_attachments", get_type=bool, default=True),
        )


class SlackJira(object):
    """
    Object stores an authenticated JIRA instance and provides methods
    that are useful in retrieving summary information of JIRA issues.
    """
    # Default section to parse information from
    JIRA_SECTION = "jira"

    JIRA_TICKET_RE_STR = "[A-Z]{1,10}-[0-9]+"
    JIRA_TICKET_RE = re.compile(JIRA_TICKET_RE_STR, re.IGNORECASE)

    def __init__(self, authed_jira):
        """
        :type authed_jira: jira.JIRA
        :param authed_jira: An authenticated jira.JIRA object that will be used
            to obtain information about various JIRA issues.
        """

        # Store the authenticated jira instance for future queries
        self._jira = authed_jira
        # Store all known projects so we only query issues in known projects
        self._projects_lookup = self.get_project_lookup()

    @property
    def jira(self):
        """
        :rtype: jira.JIRA
        :return: Property provides direct access to the authenticated JIRA object
        """
        return self._jira

    def is_project(self, project):
        """
        Does the specified project exist

        :type project: str
        :param project: The project key as defined in JIRA, i.e, if the issue is
            ISSUE-1337 then the project would be "ISSUE"

        :rtype: bool
        :return: Boolean signifying if the project was found
        """
        return self._projects_lookup.get(project, False)

    def get_project_lookup(self):
        return {getattr(k, "key"): True for k in self._jira.projects()}

    def get_projects(self, refresh=False):
        """
        Get a list of all the available projects.

        :type refresh: bool
        :param refresh: If True, returns a non cached copy of the projects and will
            store the new project lookup dict.

        :rtype: list
        :return: Returns a list of all the known projects in the JIRA server
        """
        if refresh:
            self._projects_lookup = self.get_project_lookup()

        return self._projects_lookup.keys()

    def __get_attr_helper(self, object, field, default=None):
        """
        Helper method is needed to call hasattr first and then calling getattr
        with a default value.

        The __getattr__ method is supposed to handle a default case, but it
        seems like it is not written properly (yet) :-(
        """
        # TODO: Make PR to fix this ^ bug
        if hasattr(object, field):
            return getattr(object, field)

        return default

    def get_summary(self, issue):
        """
        Get the general summary of a JIRA issue.

        :type issue: str
        :param issue: The issue key in JIRA.  This is typically a value that contains
            a string, then a hyphen, then numbers such as "ISSUE-1337".

        :rtype: JiraIssueSummary|None
        :return: A JiraIssueSummary namedtuple (if the issue was valid and found) otherwise
            None is returned
        """
        # Ensure that we do have a valid issue
        if not self.JIRA_TICKET_RE.match(issue):
            return logger.warning("Attempted to retrieve invalid ticket: %s", issue)

        project, number = issue.split("-")
        project = project.upper()

        # Ensure that we only attempt to retrieve valid issues
        if not self.is_project(project):
            return logger.warning("Attempted to retrieve invalid ticket: %s", issue)

        try:
            result = self._jira.issue(
                issue,
                fields=[
                    "summary",
                    "description",
                    "priority",
                    "status",
                    "timetracking",
                    "assignee",
                ],
            )
        except jira.JIRAError as e:
            logger.error("Error loading issue {}: {}".format(issue, e))
            return None

        assignee = None
        if result.fields.assignee:
            assignee = self.__get_attr_helper(result.fields.assignee, "displayName")

        return JiraIssueSummary(
            issue=issue,
            title=result.fields.summary,
            status=result.fields.status,
            priority=result.fields.priority,
            description=result.fields.description,
            link=result.permalink(),
            assignee=assignee,
            original_estimate=self.__get_attr_helper(
                result.fields.timetracking, "originalEstimate"
            ),
            remaining_estimate=self.__get_attr_helper(
                result.fields.timetracking, "remainingEstimate"
            )
        )

    @staticmethod
    def from_config(conf, jira_section=JIRA_SECTION):
        """
        Instantiates a JiraSlack object from a ConfigParser object.

        The ConfigParser must be extracted from a config that looks like the following:
        [jira]
        server = The JIRA server location
        access_token = The OAUTH access token (obtained by doing the OAUTH dance)
        access_token_secret = The OAUTH access token secret (obtained by doing the OAUTH dance)
        consumer_key = The JIRA consumer key as defined in JIRA
        key_cert_path = The path to the private key of the key pair used to configure in JIRA

        Additional documentation can be found in `settings.template.ini`

        :type conf: ConfigParser.ConfigParser
        :param conf: The config object to parse settings from
        :type jira_section: str
        :param jira_section: The section in the config where the jira settings are located

        :rtype: SlackJira
        :return: An instantiated SlackJira from the config parser.

        :raises JiraError: If there was an error instantiated the JIRA object
        :raises ConfigError: If there was an error parsing the config file
            (perhaps a configuration was missing)
        """
        oauth_dict = {
            k: get_config_value(conf, jira_section, k)
            for k in ("access_token", "access_token_secret", "consumer_key")
        }
        # Load the private key certificate
        key_cert_file_path = get_config_value(conf, jira_section, "key_cert_path")
        try:
            with open(key_cert_file_path) as fp:
                oauth_dict["key_cert"] = fp.read()
        except IOError as e:
            raise ConfigError(str(e))

        server_location = get_config_value(conf, jira_section, "server")
        try:
            return SlackJira(jira.JIRA(server=server_location, oauth=oauth_dict))
        except jira.JIRAError as e:
            raise JiraError(e)


class SlackBotConfig(object):
    def __init__(self, api_token, slackbot_plugins, bot_emoji=None, bot_icon=None, errors_to=None):
        self._api_token = api_token
        self._bot_emoji = bot_emoji
        self._bot_icon = bot_icon
        self._errors_to = errors_to
        self._slackbot_plugins = slackbot_plugins

    def load_into_settings_module(self, settings_module):
        """
        Loads the appropriate settings into the module specified.

        We need to load the settings into the setting module because we cannot inject the
        settings into the actual bot object... :(

        Perhaps a PR will be created to allow that...

        :param settings_module: The settings module
        :type settings_module: module
        """

        if self._api_token:
            settings_module.API_TOKEN = self._api_token

        if self._bot_emoji:
            settings_module.BOT_EMOJI = self._bot_emoji

        if self._bot_icon:
            settings_module.BOT_ICON = self._bot_icon

        if self._errors_to:
            settings_module.ERRORS_TO = self._errors_to

        # TODO: Perhaps figure out a better way to do this...
        settings_module.PLUGINS = set(self._slackbot_plugins)

    @staticmethod
    def from_config(conf, section="slackbot"):
        """
        Loads the slack options from a ConfigParser object.

        :param conf: ConfigParser object with slackbot settings
        :type conf: ConfigParser.ConfigParser
        :param section: The section to extract settings from.  Defaults to "slackbot"
        :type section: str

        :rtype: SlackBotConfig
        :return: A loaded SlackBotConfig object with the options parsed from the configparser.

        :raises: ConfigError: When the config did not contain the specified section
            or required options.
        """
        get_conf = functools.partial(get_config_value, conf, section)

        conf_slackbot_plugins = get_conf("slackbot_plugins")
        plugins = [p.strip() for p in conf_slackbot_plugins.split(",")]

        return SlackBotConfig(
            api_token=get_conf("api_token"),
            slackbot_plugins=plugins,
            bot_emoji=get_conf("bot_emoji", required=False),
            bot_icon=get_conf("bot_icon", required=False),
            errors_to=get_conf("errors_to", required=False),
        )
