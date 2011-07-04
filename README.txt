This package implements an ESI Processor as a WSGI middeware. It is primarily
aimed at development environments to simulate the production ESI Processor.

The relevant specifications and documents are:
    - http://www.w3.org/TR/esi-lang
    - http://www.akamai.com/dl/technical_publications/esi_faq.pdf

Completeness
------------

This implementation currently only implements <esi:include>.

Performance
-----------

Realistically, under standard Python, WSGI middleware is synchronous. For an
ESI Processor to reach very high levels of performance, it is probably
necessary for it to be asynchronous. That probably puts an upper limit on the
perfomance of this middleware.

However, depending on the situation, it may be performant enough.

Usage
-----

    >>> from wesgi import MiddleWare
    >>> from wsgiref.simple_server import demo_app

To use it in it's default configuration for a development server:

    >>> app = MiddleWare(demo_app)

To simulate an Akamai Production environment:
    
    >>> app = MiddleWare(demo_app, policy='akamai')

If you wish to use it for a production server, it's advisable to turn debug
mode off:
    
    >>> app = MiddleWare(demo_app, debug=False)
