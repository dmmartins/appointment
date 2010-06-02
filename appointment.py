#!/usr/bin/env python
#-*- coding: utf-8 -*-

''' Appointments. '''

import os
import datetime
import functools

# GAE imports
from google.appengine.api import users
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

    @property
    def dates(self):
        return ', '.join([d.strftime(settings.DATETIME_FORMAT) for d in self.date_list])


class Invite(db.Model):
    ''' Contact invited to an appointment. '''
    email = db.EmailProperty(required=True)
    date = db.DateTimeProperty(required=True)
    status = db.StringProperty(required=True)
    appointment = db.ReferenceProperty(Appointment)


# Login required decorator
def login_required(method, admin=False):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        user = users.get_current_user()
        if not user:
            if self.request.method == 'GET':
                self.redirect(users.create_login_url(self.request.uri))
                return
            self.error(403)
        elif admin and not users.is_current_user_admin():
            self.error(403)
        else:
            return method(self, *args, **kwargs)
    return wrapper

# Administrator required decorator
def admin_required(method):
    return login_required(method, admin=True)

class BaseRequestHandler(webapp.RequestHandler):
    ''' Suplies a common template generation method. '''
    def generate(self, template_name, template_values={}):
        lang = self.request.get('lang')
        translation.activate(lang)

        values = {
            'request': self.request,
            'user': self.current_user,
            'login_url': users.create_login_url(self.request.uri),
            'logout_url': users.create_logout_url('http://%s/' % self.request.host),
            'settings': settings,
        }

        values.update(template_values)
        directory = os.path.dirname(__file__)
        path = os.path.join(directory, 'template', template_name)
        self.response.out.write(template.render(path, values, debug=_DEBUG))

    def error(self, code):
        super(BaseRequestHandler, self).error(code)
        self.response.out.write(self.response.http_status_message(code))

    @property
    def current_user(self):
        user = users.get_current_user()
        if user:
            user.administrator = users.is_current_user_admin()
        return user


class HomeHandler(BaseRequestHandler):
    def get(self):
        if self.current_user:
            self.redirect('/new')
        else:
            self.generate('index.html')


class NewAppointmentHandler(BaseRequestHandler):
    @login_required
    def get(self):
        key = self.request.get('key')
        if key:
            appointment = Appointment.get(key)
        else:
            appointment = None

        self.generate('new.html', {'appointment': appointment})

    @login_required
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
    @admin_required
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


class Http404(BaseRequestHandler):
    def get(self):
        return self.error(404)


if __name__ == '__main__':
    application = webapp.WSGIApplication([
        (r'/', HomeHandler),
        (r'/new', NewAppointmentHandler),
        (r'/appointment', AppointmentHandler),
        (r'/appointments', AppointmentsHandler),
        (r'/availability', AvailabilityHandler),
        (r'/.*', Http404),
        ], debug=_DEBUG)
    run_wsgi_app(application)

