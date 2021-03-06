# This file is part of beets.
# Copyright 2013, Adrian Sampson.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""Allows inline path template customization code in the config file.
"""
import logging
import traceback

from beets.plugins import BeetsPlugin
from beets.library import Item, Album
from beets import config

log = logging.getLogger('beets')

FUNC_NAME = u'__INLINE_FUNC__'

class InlineError(Exception):
    """Raised when a runtime error occurs in an inline expression.
    """
    def __init__(self, code, exc):
        super(InlineError, self).__init__(
            (u"error in inline path field code:\n" \
             u"%s\n%s: %s") % (code, type(exc).__name__, unicode(exc))
        )

def _compile_func(body):
    """Given Python code for a function body, return a compiled
    callable that invokes that code.
    """
    body = u'def {0}():\n    {1}'.format(
        FUNC_NAME,
        body.replace('\n', '\n    ')
    )
    code = compile(body, 'inline', 'exec')
    env = {}
    eval(code, env)
    return env[FUNC_NAME]

def _record(obj):
    """Get a dictionary of values for an Item or Album object.
    """
    if isinstance(obj, Item):
        return dict(obj.record)
    else:
        return dict(obj._record)

def compile_inline(python_code):
    """Given a Python expression or function body, compile it as a path
    field function. The returned function takes a single argument, an
    Item, and returns a Unicode string. If the expression cannot be
    compiled, then an error is logged and this function returns None.
    """
    # First, try compiling as a single function.
    try:
        code = compile(u'({0})'.format(python_code), 'inline', 'eval')
    except SyntaxError:
        # Fall back to a function body.
        try:
            func = _compile_func(python_code)
        except SyntaxError:
            log.error(u'syntax error in inline field definition:\n%s' %
                      traceback.format_exc())
            return
        else:
            is_expr = False
    else:
        is_expr = True

    if is_expr:
        # For expressions, just evaluate and return the result.
        def _expr_func(obj):
            if not isinstance(obj, Item):
                return u''
            values = _record(obj)
            try:
                return eval(code, values)
            except Exception as exc:
                raise InlineError(python_code, exc)
        return _expr_func
    else:
        # For function bodies, invoke the function with values as global
        # variables.
        def _func_func(obj):
            if not isinstance(obj, Item):
                return u''
            func.__globals__.update(_record(obj))
            try:
                return func()
            except Exception as exc:
                raise InlineError(python_code, exc)
        return _func_func

class InlinePlugin(BeetsPlugin):
    def __init__(self):
        super(InlinePlugin, self).__init__()

        config.add({
            'pathfields': {},
        })

        # Add field expressions.
        for key, view in config['pathfields'].items():
            log.debug(u'adding template field %s' % key)
            func = compile_inline(view.get(unicode))
            if func is not None:
                self.template_fields[key] = func
