SlackJira
^^^^^^^^^

The purpose of this repository is to provide users an easy way to run a slackbot that
provides information about JIRA tickets when one is mentioned on slack.

All that is required is the credentials for JIRA and the API token for a slackbot.

.. image:: https://raw.githubusercontent.com/rastii/SlackJira/master/docs/images/slack_jira_short_summary_example.png
    :alt: Short summary jira issue mention
    :width: 100%
    :align: center


Installation & Running
----------------------

Install the package requirements.

.. code-block:: bash

    $ python setup.py develop

Configure ``settings.ini`` based on ``settings.template.ini``.
For more information about settings, please see
the `configuration`_ section.

After configuring the settings, run the slackbot:

.. code-block:: bash

    $ python run.py -c settings.ini


Configuration
-------------

All of the configurations for the slackbot can be found in the ``settings.template.ini`` file.

.. literalinclude:: https://raw.githubusercontent.com/rastii/SlackJira/master/settings.ini.template
    :language: ini
    :lines: 3-46
