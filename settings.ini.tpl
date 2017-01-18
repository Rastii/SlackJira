# This is a template for settings

[slackbot]
api_token = <slack api token>

[jira_message_handler]
# Following are defaults
max_issues = 5
response_threshold = 900
ticket_cache_size = 5

[jira]
server = <jira server>
access_token = <jira oauth access token>
access_token_secret = <jira oauth token secret>
consumer_key = <jira consumer key>
key_cert_path = <path to jira private key>

# The following is a default configuration for logging.
# Please feel free to modify as needed.
[loggers]
keys = root

[handlers]
keys = console_handler, file_handler

[formatters]
keys = simple_formatter

[logger_root]
level = DEBUG
handlers = console_handler, file_handler

[handler_console_handler]
class = logging.StreamHandler
level = INFO
formatter = simple_formatter
args=(sys.stdout,)

[handler_file_handler]
class = logging.FileHandler
level = DEBUG
formatter = simple_formatter
args = ("debug.log",)

[formatter_simple_formatter]
format=%(asctime)s - %(name)s - %(levelname)s - %(message)s

