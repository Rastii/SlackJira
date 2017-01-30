import logging
import collections
import re
import time


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

    DEFAULT_MAX_ISSUES = 5
    DEFAULT_RESPONSE_THRESHOLD = 900
    DEFAULT_TICKET_CACHE_SIZE = 5

    def __init__(self, slack_jira, max_issues=None, response_threshold=None,
                 ticket_cache_size=None):
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
        self._response_threshold = response_threshold
        self._max_issues = max_issues
        self._channel_cache = collections.defaultdict(lambda: LimitedDict(ticket_cache_size))

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
            "color": JiraMessageHandler.status_name_to_color(status),
        }

        return attachment

    def _do_handle_jira_match(self, channel_id, issue, attachment_func):
        last_mention = self._channel_cache[channel_id].get(issue)
        now = int(time.time())

        # Make sure that this ticket was last mentioned outside of our
        # minimium response threshold
        if last_mention and (now - self._response_threshold) <= last_mention:
            return

        summary = self._slack_jira.get_summary(issue)
        # We only want to handle valid issues that return real tickets
        if not summary:
            return

        # Finally, issue was not mentioned recently and is valid
        self._channel_cache[channel_id][issue] = now
        return attachment_func(summary)

    def handle_short_issue_mention(self, message):
        """
        Handles issue mentions in a message and respons with "short" message attachments.

        :param message: The message, as returned by slackbot
        """
        issues = [i.upper() for i in self.JIRA_ISSUE_RE.findall(message.body.get("text", ""))]

        # If we exceed our max jira mentions in one message, ignore the message
        if len(issues) > self._max_issues:
            logger.debug("Ignoring issue mentions %s, exceeded max issues threshold", issues)
            return

        attachments = []
        channel_id = message.body.get("channel")

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
