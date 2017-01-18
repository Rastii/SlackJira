"""
This module is used to configure the slackbot for jira responses.

This is where we define what the bot should listen to and how to respond
specifically for JIRA tickets.
"""
import re

import slackbot.settings
from slackbot import bot

import slack_jira.resources
import slack_jira.handlers


def get_jira_msg_handler(conf=None):
    if not conf:
        conf = slackbot.settings.SLACK_JIRA_CONF

    authorized_slack_jira = slack_jira.resources.SlackJira.from_config(conf)
    jira_msg_handler_config = slack_jira.resources.JiraMsgHandlerConfig.from_config(conf)
    return slack_jira.handlers.JiraMessageHandler(
        slack_jira=authorized_slack_jira,
        max_issues=jira_msg_handler_config.max_issues,
        response_threshold=jira_msg_handler_config.response_threshold,
        ticket_cache_size=jira_msg_handler_config.ticket_cache_size,
    )


jira_msg_handler = get_jira_msg_handler()


@bot.listen_to(slack_jira.handlers.JiraMessageHandler.JIRA_ISSUE_RE_STR, re.IGNORECASE)
def jira_match(message):
    jira_msg_handler.handle_short_issue_mention(message)
