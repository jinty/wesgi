import os

from setuptools import setup, find_packages

_here = os.path.dirname(__file__)

_readme = os.path.join(_here, 'README.txt')
_readme = open(_readme, 'r').read()

setup(name='wesgi',
      version='0.6dev',
      description='A WSGI middleware which processes ESI directives',
      url="http://pypi.python.org/pypi/wesgi",
      long_description=_readme,
      classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Middleware",
        "Programming Language :: Python :: 2.5",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        ],
      keywords='web middleware wsgi esi',
      author="Brian Sutherland",
      author_email="brian@vanguardistas.net",
      packages=find_packages(),
      install_requires=["WebOb",
                        "mock"],
      include_package_data=True,
      zip_safe=False,
      test_suite="wesgi.tests",
      )

