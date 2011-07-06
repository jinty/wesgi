This package implements an ESI Processor as a WSGI middeware. It is primarily
aimed at development environments to simulate the production ESI Processor.

The relevant specifications and documents are:
    - http://www.w3.org/TR/esi-lang
    - http://www.akamai.com/dl/technical_publications/esi_faq.pdf

Completeness
============

This implementation currently only implements <esi:include>.

Performance
===========

Realistically, under standard Python, WSGI middleware is synchronous. For an
ESI Processor to reach very high levels of performance, it is probably
necessary for it to be asynchronous. That probably puts an upper limit on the
perfomance of this middleware.

However, depending on the situation, it may be performant enough.

Usage
=====

    >>> from wesgi import MiddleWare
    >>> from wsgiref.simple_server import demo_app

To use it in it's default configuration for a development server:

    >>> app = MiddleWare(demo_app)

To simulate an Akamai Production environment:
    
    >>> app = MiddleWare(demo_app, policy='akamai')

To simulate an Akamai Production environment with "chase redirect" turned on:
    
    >>> from wesgi import AkamaiPolicy
    >>> policy = AkamaiPolicy()
    >>> policy.chase_redirect = True
    >>> app = MiddleWare(demo_app, policy=policy)

If you wish to use it for a production server, it's advisable to turn debug
mode off and enable some kind of cache:
    
    >>> from wesgi import LRUCache
    >>> from wesgi import Policy
    >>> policy.cache = LRUCache()
    >>> app = MiddleWare(demo_app, debug=False, policy=policy)

The LRUCache is a memory based cache using an approximation of the LRU
algorithm. The good parts of it were inspired by Raymond Hettinger's lru_cache
recipe.

Other available caches that can be easily integrated are httplib2's FileCache
or memcache. See the httplib2 documentation for details.
