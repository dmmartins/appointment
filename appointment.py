#!/usr/bin/env python
#-*- coding: utf-8 -*-

''' Appointments. '''

import os
import datetime
import gettext

# GAE imports
from google.appengine.api import mail
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from django.utils import simplejson

# Use Django translation
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
from django.conf import settings as django_settings
django_settings._target = None
from django.utils import translation

# Project imports
import settings

# Add custom Django template filters/tags
template.register_template_library('templatetags')


_DEBUG = True


class Appointment(db.Model):
    ''' Appointment. '''
    description = db.StringProperty(required=True)
    invitee_list = db.ListProperty(db.Email, required=True)
    date_list = db.ListProperty(datetime.datetime)
    name = db.StringProperty(required=True)
    email = db.EmailProperty(required=True)


class Invite(db.Model):
    ''' Contact invited to an appointment. '''
    email = db.EmailProperty(required=True)
    date = db.DateTimeProperty(required=True)
    status = db.StringProperty(required=True)
    appointment = db.ReferenceProperty(Appointment)


class BaseRequestHandler(webapp.RequestHandler):
    ''' Suplies a common template generation method. '''
    def generate(self, template_name, template_values={}):
        lang = self.request.get('lang')
        translation.activate(lang)
        values = {
            'request': self.request,
            'settings': settings,
        }

        values.update(template_values)
        directory = os.path.dirname(__file__)
        path = os.path.join(directory, 'template', template_name)
        self.response.out.write(template.render(path, values, debug=_DEBUG))

    def error(self, code):
        super(BaseRequestHandler, self).error(code)
        self.response.out.write(self.response.http_status_message(code))


class HomeHandler(BaseRequestHandler):
    def get(self):
        key = self.request.get('key')
        if key:
            appointment = Appointment.get(key)
        else:
            appointment = None

        self.generate('index.html', {'appointment': appointment})

    def post(self):
        description = self.request.get('description')
        invitees = self.request.get('invitees')
        invitee_list = [db.Email(i.strip()) for i in invitees.split(',')]
        dates = self.request.get_all('date[]')
        times = self.request.get_all('time[]')
        datetimes = map(lambda d, t: '%s %s' % (d, t), dates, times)
        date_list = [datetime.datetime.strptime(d, settings.DATETIME_FORMAT) for d in datetimes]
        name = self.request.get('name')
        email = self.request.get('email')

        # Save appointment
        appointment = Appointment(
            description=description,
            invitee_list=invitee_list,
            date_list=date_list,
            name=name,
            email=email,
            )
        appointment.put()

        # Send a confirmation email
        msg = mail.EmailMessage()
        msg.subject = 'Confirmation: %s' % appointment.description
        msg.sender = settings.app_config['email']
        msg.to = appointment.email
        directory = os.path.dirname(__file__)
        path = os.path.join(directory, 'template', 'confirmation.html')
        msg.html = template.render(path, {
            'appointment': appointment,
            'settings': settings,
            'request': self.request})
        msg.send()

        # Save invitees
        for date in date_list:
            owner = Invite(
                email=appointment.email,
                date=date,
                appointment=appointment,
                status='yes'
                )
            owner.put()

            for invitee in invitee_list:
                i = Invite(
                    email=invitee,
                    date=date,
                    appointment=appointment,
                    status='maybe'
                    )
                i.put()

        #self.redirect('/appointment?key=%s&user=%s' % (appointment.key(), appointment.email))
        self.generate('created.html')


class AppointmentHandler(BaseRequestHandler):
    def get(self):
        key = self.request.get('key')
        user = self.request.get('user')
        appointment = Appointment.get(key)
        if not appointment:
            return self.error(404)
        invitees = Invite.all().filter('appointment =', appointment)
        self.generate('appointment.html', {'appointment': appointment, 'invitees': invitees, 'user': user})


class AppointmentsHandler(BaseRequestHandler):
    def get(self):
        appointments = Appointment.all().order('-date_list')
        self.generate('appointment_list.html', {'appointments': appointments})

class AvailabilityHandler(BaseRequestHandler):
    def get(self):
        ''' Get user availability. '''
        key = self.request.get('key')
        email = self.request.get('email')
        user = self.request.get('user')
        d = self.request.get('date')
        date = datetime.datetime.strptime(d, settings.DATETIME_FORMAT)
        appointment = Appointment.get(key)
        if not appointment:
            return self.error(404)
        invitee = Invite.all().filter('email =', email).filter('date =', date).filter('appointment =', appointment).get()
        if not invitee:
            return self.error(404)
        if user == invitee.email:
            self.generate('setavailability.html', {'invitee': invitee})
        else:
            self.generate('availability.html', {'invitee': invitee})

    def post(self):
        ''' Change user availability. '''
        key = self.request.get('key')
        user = self.request.get('user')
        d = self.request.get('date')
        date = datetime.datetime.strptime(d, settings.DATETIME_FORMAT)
        availability = self.request.get('availability')
        appointment = Appointment.get(key)
        if not appointment:
            return self.error(404)
        invitee = Invite.all().filter('email =', user).filter('date =', date).filter('appointment =', appointment).get()
        if not invitee:
            return self.error(404)
        invitee.status = availability
        invitee.put()


class ConfirmHandler(BaseRequestHandler):
    ''' Confirm the appointment and send email invitation to all invitees. '''
    def get(self):
        key = self.request.get('key')
        appointment = Appointment.get(key)
        if not appointment:
            return self.error(404)

        # Send the overview e-mail
        msg = mail.EmailMessage()
        msg.subject = 'Overview: %s' % appointment.description
        msg.sender = settings.app_config['email']
        msg.to = appointment.email
        directory = os.path.dirname(__file__)
        path = os.path.join(directory, 'template', 'overview.html')
        msg.html = template.render(path, {
            'appointment': appointment,
            'settings': settings,
            'request': self.request})
        msg.send()

        # Send an email invitation for each invitee
        for invitee in appointment.invitee_list:
            msg = mail.EmailMessage()
            msg.subject = 'Invitation: %s' % appointment.description
            msg.sender = settings.app_config['email']
            msg.to = invitee
            directory = os.path.dirname(__file__)
            path = os.path.join(directory, 'template', 'invitation.html')
            msg.html = template.render(path, {
                'appointment': appointment,
                'invitee': invitee,
                'settings': settings,
                'request': self.request})
            msg.send()

        self.redirect('/appointment?key=%s&user=%s' % (appointment.key(), appointment.email))


if __name__ == '__main__':
    application = webapp.WSGIApplication([
        (r'/', HomeHandler),
        (r'/appointment', AppointmentHandler),
        (r'/appointments', AppointmentsHandler),
        (r'/availability', AvailabilityHandler),
        (r'/confirm', ConfirmHandler),
        ], debug=_DEBUG)
    run_wsgi_app(application)

