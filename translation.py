#!/usr/bin/env python
#-*- coding: utf-8 -*-

from gettext import translation

# Initialise with no translation
_ = lambda x: x

def gettext(msg):
    return _(msg)

def activate(lang):
    global _
    if lang:
        try:
            _ = translation('gae', 'locale', languages=[lang]).ugettext
        except IOError:
            _ = lambda x: x
    else:
        _ = lambda x: x

