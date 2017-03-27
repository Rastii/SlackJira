SlackJira
^^^^^^^^^

An easy to run bot that provides users of slack information about JIRA tickets when
mentioned.

All that is required is the credentials for JIRA and the API token for a slackbot.


Bot Responses
-------------
The bot will respond with either a short message:

.. image:: https://raw.githubusercontent.com/rastii/SlackJira/master/docs/images/slack_jira_short_summary_example.png
    :alt: Short summary jira issue mention
    :width: 100%
    :align: center

or with a longer response:

.. image:: https://raw.githubusercontent.com/rastii/SlackJira/master/docs/images/slack_jira_long_summary_example.png
    :alt: Long summary jira issue mention
    :width: 100%
    :align: center

This is entirely based on whether or not a "!" prefix exists before the ticket.  For example,
"TICK-1337" will respond with a short message, which includes the following information:
* Ticket
* Ticket title (that is also a link to the ticket)
* Priority
* Status
* Assignee

The longer response also includes the **description** of the ticket and **time logging**
information (if it is available).


Installation & Running
----------------------

To install from github, please use the following commands:

.. code-block:: bash

    $ git clone git@github.com:Rastii/SlackJira.git
    $ cd SlackJira
    $ python setup.py build
    $ sudo python setup.py install

Configure ``settings.ini`` based on ``settings.template.ini``.
For more information about settings, please see
the ``settings.template.ini`` file.

After configuring the settings, run the slackbot:

.. code-block:: bash

    $ slack_jira -c settings.ini
