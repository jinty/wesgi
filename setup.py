from setuptools import setup, find_packages

setup(name='wesgi',
      version='0.1',
      description='A WSGI middleware which processes ESI directives',
      classifiers=[
        "Development Status :: 2 - Pre-Alpha Development ",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
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

