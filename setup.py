import setuptools
import codecs
from os import path


here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with codecs.open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()


setuptools.setup(
    name="slack_jira",
    version="0.0.1",
    description="Easily configurable slack bot runner for displaying info/links of JIRA tickets",
    long_description=long_description,
    url="https://github.com/Rastii/SlackJira",
    author="rastii",
    license="MIT",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Communications :: Chat",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 2.7",
    ],
    keywords="slack jira bot",
    # TODO: If docs / tests are added then exclude them!
    packages=setuptools.find_packages(exclude=["docs"]),
    install_requires=[
        "PyJWT>=1.4.2",
        "argparse>=1.2.1",
        "backports.ssl-match-hostname>=3.5.0.1",
        "cffi>=1.9.1",
        "cryptography>=1.7.1",
        "enum34>=1.1.6",
        "idna>=2.2",
        "ipaddress>=1.0.18",
        "jira>=1.0.7",
        "oauthlib>=2.0.1",
        "pyasn1>=0.1.9",
        "pycparser>=2.17",
        "pycrypto>=2.6.1",
        "requests>=2.12.4",
        "requests-oauthlib>=0.7.0",
        "requests-toolbelt>=0.7.0",
        "six>=1.10.0",
        "slackbot>=0.4.1",
        "slacker>=0.9.30",
        "tlslite>=0.4.9",
        "websocket-client>=0.40.0",
        "wsgiref>=0.1.2",
    ],
)
