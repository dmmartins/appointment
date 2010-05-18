#!/usr/bin/env python
#-*- coding: utf-8 -*-

''' Appointments. '''

import os
import datetime
import gettext

# GAE imports
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

# Use Django translation
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
from django.conf import settings
settings._target = None
from django.utils import translation

# Add custom Django template filters/tags
template.register_template_library('templatetags')


_DEBUG = True


class Appointment(db.Model):
    ''' Appointment. '''
    description = db.StringProperty(required=True)
    invitees = db.ListProperty(db.Email, required=True)
    dates = db.ListProperty(datetime.datetime)
    name = db.StringProperty(required=True)
    email = db.EmailProperty(required=True)


class Invitee(db.Model):
    ''' Person invited to an appointment. '''
    email = db.EmailProperty(required=True)
    status = db.StringProperty(required=True)
    appointment = db.ReferenceProperty(Appointment)


class BaseRequestHandler(webapp.RequestHandler):
    ''' Suplies a common template generation method. '''
    def generate(self, template_name, template_values={}):
        lang = self.request.get('lang')
        translation.activate(lang)
        values = {
            'request': self.request,
            'user': self.current_user,
            'settings': {'TITLE': 'Appointments'},
        }

        values.update(template_values)
        directory = os.path.dirname(__file__)
        path = os.path.join(directory, 'template', template_name)
        self.response.out.write(template.render(path, values, debug=_DEBUG))

    @property
    def current_user(self):
        return self.get_cookie('user')

    def error(self, code):
        super(BaseRequestHandler, self).error(code)
        self.response.out.write(self.response.http_status_message(code))

    def set_cookie(self, name, value):
        self.response.headers.add_header('Set-Cookie', 'user=%s' % value)

    def get_cookie(self, name):
        return self.request.cookies.get('user')


class HomeHandler(BaseRequestHandler):
    def get(self):
        key = self.request.get('key')
        if key:
            appointment = Appointment.get(key)
        else:
            appointment = None

        self.generate('index.html', {'appointment': appointment})


class AppointmentHandler(BaseRequestHandler):
    def get(self):
        key = self.request.get('key')
        user = self.request.get('user')


if __name__ == '__main__':
    application = webapp.WSGIApplication([
        (r'/', HomeHandler),
        (r'/appointment', AppointmentHandler),
        ], debug=_DEBUG)
    run_wsgi_app(application)

