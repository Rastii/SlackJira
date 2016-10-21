import ConfigParser
import time
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


def get_config_value(config_parser, section, option):
    """
    Retrieves a config value from a config parser.

    :type config_parser: ConfigParser.ConfigParser
    :param config_parser: The config parser object instance to extract values from
    :type section: str
    :param section: The section to extract values from
    :type option: str
    :param option: The option to extract a value from

    :rtype: str
    :return: The value extracted from the ConfigParser object

    :raises ConfigError: When the ConfigParser did not contain the specified value
        based on the section and option
    """
    try:
        value = config_parser.get(section, option)
    except ConfigParser.Error:
        raise ConfigError("Missing configuration '{}' in section '{}'".format(option, section))

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


class SlackJira(object):
    """
    Object stores an authenticated JIRA instance and provides methods
    that are useful in retrieving summary information of JIRA issues.
    """
    # Default section to parse information from
    OAUTH_SECTION = "oauth"
    SERVER_SECTION = "server"

    JIRA_TICKET_RE_STR = "[A-Z]{1,10}-[0-9]+"
    JIRA_TICKET_RE = re.compile(JIRA_TICKET_RE_STR, re.IGNORECASE)

    # Required fields in config parser
    # TODO: Make this work with other methods other than OAUTH
    SERVER_FIELDS = (
        "server"
    )
    OAUTH_FIELDS = (
        "access_token",
        "access_token_secret",
        "consumer_key",
        "key_cert"
    )

    def __init__(self, authed_jira):
        """
        :type authed_jira: jira.JIRA
        :param authed_jira: An authenticated jira.JIRA object that will be used
            to obtain information about various JIRA issues.
        """

        # Store the authenticated jira instance for future queries
        self.__jira = authed_jira
        # Store all known projects so we only query issues in known projects
        self.__projects_lookup = self.get_project_lookup()

    @property
    def jira(self):
        """
        :rtype: jira.JIRA
        :return: Property provides direct access to the authenticated JIRA object
        """
        return self.__jira

    def is_project(self, project):
        """
        Does the specified project exist

        :type project: str
        :param project: The project key as defined in JIRA, i.e, if the issue is
            ISSUE-1337 then the project would be "ISSUE"

        :rtype: bool
        :return: Boolean signifying if the project was found
        """
        return self.__projects_lookup.get(project, False)

    def get_project_lookup(self):
        return {getattr(k, "key"): True for k in self.__jira.projects()}

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
            self.__projects_lookup = self.get_project_lookup()

        return self.__projects_lookup.keys()

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
            result = self.__jira.issue(
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
    def from_config(conf, oauth_section=OAUTH_SECTION, server_section=SERVER_SECTION,
                    newline_encoding="|"):
        """
        Instantiates a JiraSlack object from a ConfigParser object.

        This includes parsing out OAUTH credentials and the server location AND
        authenticating to the server with the provided credentials.  The authenticated
        JIRA object is then injected into the SlackJira object.

        NOTE: Due to the way INI files work, the key_cert value must NOT contain any
              newline characters.  Instead, please "encode" the newline characters as
              a different (non base64 character).  The default for this is a "|" (PIPE)
              character.  Ultimately, this can be defined as the `newline_encoding` param

        There needs to be two sections in the config file, the first section contains
        server information such as the following:

        [server]
        server = <ip_of_server>

        The second section needs the oauth credentials, such as the following:

        [oauth]
        access_token = The OAUTH access token (obtained by doing the OAUTH dance)
        access_token_secret = The OAUTH access token secret (obtained by doing the OAUTH dance)
        consumer_key = The JIRA consumer key as defined in JIRA
        key_cert = The private key of the key pair used to configure in JIRA

        :type conf: ConfigParser.ConfigParser
        :param conf: The config object to parse settings from
        :type oauth_section: str
        :param oauth_section: The section from the config that contains
            the oauth information (optional)
        :type server_section: str
        :param server_section: The section from the config that contains
            the server information (optional)
        :type newline_encoding: str
        :param newline_encoding: The character that replaces a newline character.
            When obtaining the key_cert, this value will be replaces with newlines.

        :rtype: SlackJira
        :return: An instantiated SlackJira from the config parser.

        :raises JiraError: If there was an error instantiated the JIRA object
        :raises ConfigError: If there was an error parsing the config file
            (perhaps a configuration was missing)
        """

        oauth_dict = {k: get_config_value(conf, oauth_section, k) for k in SlackJira.OAUTH_FIELDS}
        oauth_dict["key_cert"] = oauth_dict["key_cert"].replace(newline_encoding, "\n")
        server_location = get_config_value(conf, server_section, "server")

        try:
            authed_jira = jira.JIRA(server=server_location, oauth=oauth_dict)
            lljira = SlackJira(authed_jira)

            return lljira
        except jira.JIRAError as e:
            raise JiraError(e)


class LimitedDict(collections.OrderedDict):
    """
    A dictionary that enforces a size limit and will remove the oldest item in the dictionary
    (FIFO) while the limit is exceeded.
    """
    def __init__(self, max_size, *args, **kwargs):
        super(LimitedDict, self).__init__(*args, **kwargs)
        self.__max_size = max_size

    def __setitem__(self, key, value, **kwargs):
        super(LimitedDict, self).__setitem__(key, value, **kwargs)
        self.__enforce_size_limit()

    def __enforce_size_limit(self):
        while len(self) > self.__max_size:
            self.popitem(last=False)


class JiraMessageHandler(object):
    """
    Object is responsible for handling messages that contain JIRA issues.

    The object is injected with a `SlackJira` object, which will be used to retrieve
    information about the issues that were mentioned.  If an issue is mentioned more than
    once during the `response_threshold` interval, additional information will not be
    displayed.
    """
    JIRA_ISSUE_RE_STR = "[A-Z]{1,10}-[0-9]+"
    JIRA_ISSUE_RE = re.compile(JIRA_ISSUE_RE_STR, re.IGNORECASE)
    # JIRA limits you to 20 attachments for a message, this will be the upperbound of max_issues
    MAX_JIRA_ATTACHMENTS = 20

    def __init__(self, slack_jira, max_issues=5, response_threshold=900, ticket_cache_size=5):
        """
        :type slack_jira: slack_jira.resource.SlackJira
        :param slack_jira: The initialized slack jira object that will be used to retrieve
            information about various JIRA tickets.
        :type max_issues: int
        :param max_issues: The threshold of how many issues (in a single message) to retrieve
            information and respond.  For example, if max_issues is 5 and the message looks like
            the following: "Staging: TICK-1, TICK-2, TICK-3, TICK-4, TICK-5, TICK-6", then the
            message will be ignored.
        :type response_threshold: int
        :param response_threshold: The number (in seconds) of when to retrieve information about
            a ticket since its last mention.  By default it is 900 ( 15 minutes ).  Note: this
            threshold is per channel.
        :type ticket_cache_size: int
        :param ticket_cache_size: Store this many last "mentions", that is, if the threshold is 15
            minutes and the ticket_cache_size is 5 and we had 6 (seperate) tickets mentioned in
            less than 15 minutes, the response_threshold will no longer apply since the last
            response time will not be stored in the "cache".
        """
        self.__slack_jira = slack_jira
        self.__response_threshold = response_threshold

        if max_issues > self.MAX_JIRA_ATTACHMENTS:
            logger.warning(
                "Max issues specification %d exceeded JIRA attachment threshold for one message "
                "defaulting to %d threshold",
                max_issues,
                self.MAX_JIRA_ATTACHMENTS,
            )
            max_issues = self.MAX_JIRA_ATTACHMENTS

        self.__max_issues = max_issues

        self.__channel_cache = collections.defaultdict(
            lambda: LimitedDict(ticket_cache_size)
        )

    @staticmethod
    def status_name_to_color(status_name):
        """
        Returns a color based on the jira ticket status name.

        :type status_name: str
        :param status_name: The status name, for example "Open" or "In progress"

        :rtype: str
        :return: The hex representation of the status based on the values shown in
            JIRA (label colors)
        """
        # Get color based on status
        if status_name == "Open":
            # JIRA "Blue" color
            color = "#4a6785"
        elif "progress" in status_name:
            # JIRA "Yellow" color
            color = "#ffd351"
        else:
            # JIRA "Green" color
            color = "#14892c"

        return color

    @staticmethod
    def get_full_attachment(summary):
        """
        Retrieves a full attachment summary of the ticket.

        Note: this is a lot of information and should only be used when a user explicitly wants
        A LOT of information about the ticket in slack.

        Please refer to https://api.slack.com/docs/message-attachments for docs
        on slack attachments

        :type summry: JiraIssueSummary
        :param summary: A JiraIssueSummary namedtuple that will be used to produce a "full"
            attachment response for slack

        :rtype: dict
        :return: A dictionary that contains the proper key values for a slack attachment
        """
        status = summary.status.name
        attachment = {
            "title": "[{}] - {}".format(summary.issue, summary.title),
            "title_link": summary.link,
            "text": summary.description,
            "fallback": "[{}] - {}".format(summary.issue, summary.title),
            "footer": "Assigned to {}".format(summary.assignee),
            "fields": [
                {
                    "title": "Priority",
                    "value": summary.priority.name,
                    "short": True
                },
                {
                    "title": "Status",
                    "value": status,
                    "short": True
                },
            ],
            "color": JiraMessageHandler.status_name_to_color(status),
        }

        if summary.original_estimate and summary.remaining_estimate:
            attachment["fields"].append({
                "title": "Original Estimate / Remaining Estimate",
                "value": "{} / {}".format(summary.original_estimate, summary.remaining_estimate),
            })

        return attachment

    @staticmethod
    def get_short_attachment(summary):
        """
        Retrieves a short attachment summary of the ticket.

        This means the title (as a link to the ticket), the status of the ticket
        and who the ticket is currently assigned to.

        Please refer to https://api.slack.com/docs/message-attachments for docs
        on slack attachments

        :type summary: JiraIssueSummary
        :param summary: A JiraIssueSummary namedtuple that will be used to produce a "short"
            attachment response for slack

        :rtype: dict
        :return: A dictionary that contains the proper key values for a slack attachment
        """
        status = summary.status.name

        # Get color based on status
        if status == "Open":
            color = "#4a6785"
        elif "progress" in status:
            color = "#ffd351"
        else:
            color = "#14892c"

        title = u"[{}] - {} - {}".format(summary.issue, status, summary.title)
        if summary.assignee:
            footer = u"Assigned to {}".format(summary.assignee)
        else:
            footer = u"This ticket is currently unassigned."

        attachment = {
            "fallback": title,
            "title": title,
            "title_link": summary.link,
            "footer": footer,
            "color": color
        }

        return attachment

    def _do_handle_jira_match(self, channel_id, issue, attachment_func):
        summary = self.__slack_jira.get_summary(issue)
        # We only want to handle valid issues that return real tickets
        if not summary:
            return

        last_mention = self.__channel_cache[channel_id].get(issue)
        now = int(time.time())

        # Make sure that this ticket was last mentioned outside of our
        # miniumum response threshold
        if not last_mention or (now - self.__response_threshold) > last_mention:
            # If it is, lets store the last mention time and get the attachment
            self.__channel_cache[channel_id][issue] = now
            return attachment_func(summary)

    def handle_short_issue_mention(self, message):
        """
        Handles issue mentions in a message and respons with "short" message attachments.

        :param message: The message, as returned by slackbot
        """
        issues = self.JIRA_ISSUE_RE.findall(message.body["text"])

        # If we exceed our max jira mentions in one message, ignore the message
        if len(issues) > self.__max_issues:
            logger.debug("Ignoring issues %s, exceeded max issues threshold", issues)
            return

        attachments = []
        channel_id = message.channel._body.get("id")

        # Iterate through all issues and create an attachment for each
        for issue in issues:
            summary_attachment = self._do_handle_jira_match(
                channel_id=channel_id,
                issue=issue,
                attachment_func=self.get_short_attachment,
            )
            if summary_attachment:
                attachments.append(summary_attachment)

        # Only respond if we have at least one valid attachment
        if attachments:
            message.send_webapi("", attachments=attachments)

