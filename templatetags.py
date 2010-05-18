#!/usr/bin/env python
#-*- coding: utf-8 -*-

from google.appengine.ext.webapp import template
import translation

def date_format(date, format=None):
    if not date:
        return ''
    if not format:
        return date
    return date.strftime(format)

def trans(text):
    return translation.gettext(text)

# Register the filter/templatetags functions
register = template.create_template_register()
register.filter(date_format)
register.simple_tag(trans)

