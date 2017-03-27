import logging
import collections
import re
import time
import functools


logger = logging.getLogger(__name__)


class LimitedDict(collections.OrderedDict):
    """
    A dictionary that enforces a size limit and will remove the oldest item in the dictionary
    (FIFO) while the limit is exceeded.
    """
    def __init__(self, max_size, *args, **kwargs):
        super(LimitedDict, self).__init__(*args, **kwargs)
        self._max_size = max_size

    def __setitem__(self, key, value, **kwargs):
        super(LimitedDict, self).__setitem__(key, value, **kwargs)
        self._enforce_size_limit()

    def _enforce_size_limit(self):
        while len(self) > self._max_size:
            self.popitem(last=False)


class JiraMessageTimer(object):
    """
    Keeps track of jira messages per channel in respect to the last time they were seen
    """
    def __init__(self, ticket_cache_size, response_threshold):
        """
        :param response_threshold: The number (in seconds) of when to retrieve information about
            a ticket since its last mention
        :type response_threshold: int
        :param ticket_cache_size: Timed issue mentions per channel modulus size
        :type ticket_cache_size: int
        """
        self._timer_cache = collections.defaultdict(lambda: LimitedDict(ticket_cache_size))
        self._response_threshold = response_threshold

    def check_issue(self, channel_id, issue):
        """
        Checks to see if an issue was not recently mentioned

        :param channel_id: The ID of the channell
        :param issue: THe JIRA ticket
        :type issue: str

        :rtype: bool
        :return: Boolean based on the validity
        """
        last_mention = self._timer_cache[channel_id].get(issue)

        if last_mention and (int(time.time()) - self._response_threshold <= last_mention):
            return False

        return True

    def log_issues(self, channel_id, issues):
        """
        Logs the issues with the current time for the specified channel id

        :param channel_id: The slack channel identifier
        :param issues: Iterable sequence of issues
        """
        now = int(time.time())
        for i in issues:
            self._timer_cache[channel_id][i] = now


class JiraMessageHandler(object):
    """
    Object is responsible for handling messages that contain JIRA issues.

    The object is injected with a `SlackJira` object, which will be used to retrieve
    information about the issues that were mentioned.  If an issue is mentioned more than
    once during the `response_threshold` interval, additional information will not be
    displayed.
    """
    JIRA_ISSUE_RE_STR = "!?[A-Z]{1,10}-[0-9]+"
    JIRA_ISSUE_RE = re.compile(JIRA_ISSUE_RE_STR, re.IGNORECASE)
    # JIRA limits you to 20 attachments for a message, this will be the upper bound of max_issues
    MAX_JIRA_ATTACHMENTS = 20

    DEFAULT_MAX_ISSUES = 5
    DEFAULT_RESPONSE_THRESHOLD = 900
    DEFAULT_TICKET_CACHE_SIZE = 5

    def __init__(self, slack_jira, max_issues=None, response_threshold=None,
                 ticket_cache_size=None, full_attachments=True):
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
        :type full_attachments: bool
        :param full_attachments: Boolean that specifies whether or not to show long attachments,
            that is responding to jira tickets that prefix with ! with additional information.
        """
        if not max_issues:
            max_issues = self.DEFAULT_MAX_ISSUES
        if not response_threshold:
            response_threshold = self.DEFAULT_RESPONSE_THRESHOLD
        if not ticket_cache_size:
            ticket_cache_size = self.DEFAULT_TICKET_CACHE_SIZE

        if max_issues > self.MAX_JIRA_ATTACHMENTS:
            logger.warning(
                "Max issues specification %d exceeded JIRA attachment threshold for one message "
                "defaulting to %d threshold",
                max_issues,
                self.MAX_JIRA_ATTACHMENTS,
            )
            max_issues = self.MAX_JIRA_ATTACHMENTS

        self._slack_jira = slack_jira
        self._max_issues = max_issues
        self._message_timer = JiraMessageTimer(ticket_cache_size, response_threshold)
        self._full_attachments = full_attachments

    # TODO: Move these static methods into a separate module
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
        if "open" in status_name.lower():
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

        :type summary: JiraIssueSummary
        :param summary: A JiraIssueSummary namedtuple that will be used to produce a "full"
            attachment response for slack

        :rtype: dict
        :return: A dictionary that contains the proper key values for a slack attachment
        """
        attachment = JiraMessageHandler.get_short_attachment(summary)

        # Add full description and time estimation info to attachment
        attachment["text"] = summary.description
        if summary.original_estimate and summary.remaining_estimate:
            attachment["fields"] = [{
                "title": u"Original Estimate / Remaining Estimate",
                "value": u"{} / {}".format(summary.original_estimate, summary.remaining_estimate),
            }]

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
        footer = u"{status} - {priority} - {assigned}".format(
            status=status,
            priority=summary.priority.name,
            assigned=(
                u"This ticket is currently unassigned" if not summary.assignee else
                u"Assigned to {}".format(summary.assignee)
            )
        )

        title = u"[{}] - {}".format(summary.issue, summary.title)
        attachment = {
            "fallback": title,
            "title": title,
            "title_link": summary.link,
            "footer": footer,
            "color": JiraMessageHandler.status_name_to_color(status),
        }

        return attachment

    def _get_summaries(self, channel_id, issues):
        summaries = (
            self._slack_jira.get_summary(i)
            for i in issues if self._message_timer.check_issue(channel_id, i)
        )
        # Remove any entries that did not return a summary
        summaries = filter(None, summaries)
        # Log all of these summaries in our timer so we ignore them
        self._message_timer.log_issues(channel_id, (s.issue for s in summaries))

        return summaries

    def handle_mention(self, message):
        """
        Handle a message that contains JIRA ticket mentions and respond to it with
        attachments of JIRA summaries

        :param message: The message, as returned by slackbot
        :type message: slackbot.dispatcher.Message
        """
        issues = {i.upper() for i in self.JIRA_ISSUE_RE.findall(message.body.get("text", ""))}
        if len(issues) > self._max_issues:
            return logger.debug("Ignoring issue mentions %s, exceeded max issues threshold", issues)

        channel_id = message.body.get("channel")
        if not channel_id:
            return logger.error("Unable to acquire channel_id, ignoring message")

        get_summaries = functools.partial(self._get_summaries, channel_id)

        if not self._full_attachments:
            # TODO: Separation of long vs short attachments could be better, this will do for now
            issues = {i.replace("!", "") for i in issues}
            attachments = map(self.get_short_attachment, get_summaries(issues)) or []
        else:
            # Extract long + short issues
            long_issues = {i for i in issues if i.startswith("!")}
            short_issues = issues - long_issues
            # Generator here to effectively remove the ! since our get_summaries method
            # is agnostic to "short vs long" issues
            long_issues = (i[1:] for i in long_issues)

            # Extract JIRA summaries from the issues and convert them into attachments
            long_attachments = map(self.get_full_attachment, get_summaries(long_issues)) or []
            short_attachments = map(self.get_short_attachment, get_summaries(short_issues)) or []
            attachments = short_attachments + long_attachments

        if attachments:
            logger.info("Sent {} attachments".format(len(attachments)))
            message.send_webapi("", attachments=attachments)
