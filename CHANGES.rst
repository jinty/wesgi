CHANGES
=======

0.6 (2011-07-06)
----------------

Features
++++++++

- Major refactoring to use ``httplib2`` as the backend to get ESI includes. This
  brings along HTTP Caching.
- A memory based implementation of the LRU caching algoritm at ``wesgi.LRUCache``.
- Handle ESI comments.

Bugfixes
++++++++

- Fix bug where regular expression to find ``src:includes`` could take a long time.

0.5 (2011-07-04)
----------------

- Initial release.
