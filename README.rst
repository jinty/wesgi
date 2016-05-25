`wesgi` implements an ESI Processor as a WSGI middeware. It is primarily aimed
at development environments to simulate the production ESI Processor.  Under
certain conditions it may be used in production as well.

Completeness
============

This implementation currently only implements ``<esi:include>`` and
``<!--esi -->`` comments. The relevant specifications and documents are:

- http://www.w3.org/TR/esi-lang
- http://www.akamai.com/dl/technical_publications/esi_faq.pdf

Performance
===========

An ESI processor generally makes a lot of network calls to other services in
the process of putting together a page. So, in general, to reach very high
levels of performance it should be asynchronous. Standard Python and WSGI is
synchronous, placing an upper limit on performance which depends on the
following:

- How many threads are used
- How many ESI includes used per page
- The speed of the servers serving the ESI Includes
- Whether `wesgi` uses a cache and if the ESI includes come with Cache-Control
  headers

Depending on the situation, `wesgi` may be performant enough for you.

There are also a number of ways to run WSGI applications asynchronously, with
varying definitions of "asynchronous".

Usage
=====

Configuration via Python
------------------------

    >>> from wesgi import MiddleWare
    >>> from wsgiref.simple_server import demo_app

To use it in it's default configuration for a development server:

    >>> app = MiddleWare(demo_app)

To simulate an Akamai Production environment:
    
    >>> from wesgi import AkamaiPolicy
    >>> policy = AkamaiPolicy()
    >>> app = MiddleWare(demo_app, policy=policy)

To simulate an Akamai Production environment with "chase redirect" turned on:
    
    >>> policy.chase_redirect = True
    >>> app = MiddleWare(demo_app, policy=policy)

If you wish to use it for a production server, it's advisable to turn debug
mode off and enable some kind of cache:
    
    >>> from wesgi import LRUCache
    >>> from wesgi import Policy
    >>> policy.cache = LRUCache()
    >>> app = MiddleWare(demo_app, debug=False, policy=policy)

The ``LRUCache`` is a memory based cache using an approximation of the LRU
algorithm. The good parts of it were inspired by Raymond Hettinger's
``lru_cache`` recipe.

Other available caches that can be easily integrated are ``httplib2``'s
``FileCache`` or ``memcache``. See the ``httplib2`` documentation for details.

Configuration via paste.ini
---------------------------

The ``wesgi.filter_app_factory`` function lets you configure ``wesgi`` in your
paste.ini file. For example::

    [filter-app:wesgi]
    paste.filter_app_factory = wesgi:filter_app_factory
    cache=lru_memory
    cache_maxsize=10
    policy=akamai
    policy_chase_redirect=True
    next = myapp

Development
===========

Development on `wesgi` is centered around this github branch:

    https://github.com/jinty/wesgi
