#!/usr/bin/env python
#-*- coding: utf-8 -*-

''' Appointments. '''

import os
import datetime
import functools
import urllib

# GAE imports
from google.appengine.api import users
from google.appengine.api import mail
from google.appengine.api import images
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext import search
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import blobstore_handlers
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


class Photo(db.Model):
    ''' User photo.  '''
    user = db.UserProperty(required=True)
    blob_info = blobstore.BlobReferenceProperty(required=True)
    comment = db.StringProperty(required=False)
    public = db.BooleanProperty(required=True)
    _rotate = db.IntegerProperty(required=False, default=0)

    def _get_rotate(self):
        return self._rotate

    def _set_rotate(self, angle):
        if self._rotate == None:
            self._rotate = 0
        self._rotate = angle
        if self._rotate > 360 or self._rotate < 0:
            self._rotate %= 360
    rotate = property(_get_rotate, _set_rotate)


class File(db.Model):
    ''' User file. '''
    user = db.UserProperty(required=True)
    blob_info = blobstore.BlobReferenceProperty(required=True)
    comment = db.StringProperty(required=False)
    public = db.BooleanProperty(required=True)


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
            'current_user': self.current_user,
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
            self.redirect('/profile')
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
        name = self.current_user.nickname()
        email = self.current_user.email()

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


class PublicImagesHandler(BaseRequestHandler):
    def get(self):
        photos = Photo.all().filter('public =', True)
        self.generate('public.html', {'photos': photos})


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


class AppointmentRemoveHandler(BaseRequestHandler):
    def post(self):
        key = self.request.get('key');
        appointment = Appointment.get(key)
        if not appointment:
            return self.error(404)

        if appointment.email == self.current_user.email:
            return self.error(405)

        invitees = Invite.all().filter('appointment =', appointment)
        for invitee in invitees:
            invitee.delete()

        appointment.delete()


class ProfileHandler(BaseRequestHandler):
    ''' Profile. '''
    def get(self):
        email = self.request.get('user')
        if not email:
            user = self.current_user
        else:
            user = users.User(email)

        invitations = Appointment.all().filter('invitee_list =', user.email())
        appointments = Appointment.all().filter('email =', user.email())
        photos = Photo.all().filter('user =', user)
        if not user == self.current_user:
            photos.filter('public =', True)
        files = File.all().filter('user =', user)
        if not user == self.current_user:
            files.filter('public =', True)

        upload_url = blobstore.create_upload_url('/upload')
        self.generate('profile.html', {'photos': photos, 'files': files, 'appointments': appointments, 'invitations': invitations, 'upload_url': upload_url, 'user': user})


class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):
    ''' File uploader. '''
    @login_required
    def post(self):
        for upload, comment, public in map(lambda x, y, z: (x, y, bool(z)), self.get_uploads(), self.request.get_all('comment'), self.request.get_all('public')):
            if 'image' in upload.content_type:
                if upload.size > 1000000:
                    upload.delete()
                    self.redirect('/toolarge')
                else:
                    photo = Photo(
                        user=users.get_current_user(),
                        blob_info=upload.key(),
                        comment=comment,
                        public=public)
                    photo.put()
                    self.redirect('/profile')
            else:
                file_ = File(
                    user=users.get_current_user(),
                    blob_info=upload.key(),
                    comment=comment,
                    public=public)
                file_.put()
                self.redirect('/profile')

class TooLargeHandler(BaseRequestHandler):
    def get(self):
        self.generate('toolarge.html')


class PhotoHandler(BaseRequestHandler):
    def get(self, photo_key):
        photo = Photo.get(photo_key)
        if not photo:
            return self.error(404)

        self.generate('photo.html', {'photo': photo})


class PhotosHandler(BaseRequestHandler):
    def get(self, photo_key):
        photo = Photo.get(photo_key)
        if not photo:
            return self.error(404)

        blob_key = str(photo.blob_info.key())
        img = images.Image(blob_key=blob_key)
        img.im_feeling_lucky()
        img.rotate(photo.rotate)
        thumbnail = img.execute_transforms(output_encoding=images.JPEG)
        if img.width > 500:
            img.resize(width=500)
            thumbnail = img.execute_transforms(output_encoding=images.JPEG)
        self.response.headers['Content-Type'] = 'image/jpg'
        self.response.out.write(thumbnail)


class FullPhotoHandler(blobstore_handlers.BlobstoreDownloadHandler):
    def get(self, photo_key):
        photo = Photo.get(photo_key)
        if not photo:
            return self.error(404)

        self.send_blob(photo.blob_info)


class ThumbHandler(BaseRequestHandler):
    def get(self, photo_key):
        photo = Photo.get(photo_key)
        if not photo:
            return self.error(404)

        blob_key = str(photo.blob_info.key())
        img = images.Image(blob_key=blob_key)
        img.resize(width=150)
        img.im_feeling_lucky()
        thumbnail = img.execute_transforms(output_encoding=images.JPEG)
        self.response.headers['Content-Type'] = 'image/jpg'
        self.response.out.write(thumbnail)


class PhotoSearchHandler(BaseRequestHandler):
    def get(self):
        query = self.request.get('q')
        email = self.request.get('user')
        user = users.User(urllib.unquote(email))
        photos = (p for p in Photo.all().filter('user =', user) if query in p.comment)
        self.generate('searchresult.html', {'photos': photos, 'query': query})


class RotateHandler(BaseRequestHandler):
    @login_required
    def post(self, photo_key):
        photo = Photo.get(photo_key)
        if not photo:
            return self.error(404)

        if photo.user != self.current_user:
            return self.error(405)

        angle = int(self.request.get('angle', 0))
        photo.rotate += angle
        photo.put()


class ShareHandler(BaseRequestHandler):
    @login_required
    def post(self, photo_key):
        photo = Photo.get(photo_key)
        if not photo:
            return self.error(404)

        if photo.user != self.current_user:
            return self.error(405)

        public = bool(self.request.get('public'))
        photo.public = public
        photo.put()


class PhotoRemoveHandler(BaseRequestHandler):
    @login_required
    def post(self):
        photo_key = self.request.get('photo_key')
        photo = Photo.get(photo_key)
        if not photo:
            return self.error(404)

        if photo.user != self.current_user:
            return self.error(405)

        photo.blob_info.delete()
        photo.delete()


class FileHandler(blobstore_handlers.BlobstoreDownloadHandler):
    def get(self, file_key, file_name):
        file_ = File.get(file_key)
        if not file_:
            return self.error(404)

        self.send_blob(file_.blob_info)


class FileRemoveHandler(BaseRequestHandler):
    @login_required
    def post(self):
        file_key = self.request.get('file_key')
        file_ = File.get(file_key)
        if not file_:
            return self.error(404)

        if file_.user != self.current_user:
            return self.error(405)

        file_.blob_info.delete()
        file_.delete()


class Http404(BaseRequestHandler):
    def get(self):
        return self.error(404)


if __name__ == '__main__':
    application = webapp.WSGIApplication([
        (r'/', HomeHandler),
        (r'/new', NewAppointmentHandler),
        (r'/appointment', AppointmentHandler),
        (r'/appointment/remove', AppointmentRemoveHandler),
        (r'/appointments', AppointmentsHandler),
        (r'/availability', AvailabilityHandler),
        (r'/profile', ProfileHandler),
        (r'/profile/([^/]+)', ProfileHandler),
        (r'/upload', UploadHandler),
        (r'/public', PublicImagesHandler),
        (r'/toolarge', TooLargeHandler),
        (r'/photo/remove', PhotoRemoveHandler),
        (r'/photo/search', PhotoSearchHandler),
        (r'/photo/([^/]+)', PhotoHandler),
        (r'/photos/([^/]+)', PhotosHandler),
        (r'/photo/([^/]+)/full', FullPhotoHandler),
        (r'/thumb/([^/]+)', ThumbHandler),
        (r'/rotate/([^/]+)', RotateHandler),
        (r'/share/([^/]+)', ShareHandler),
        (r'/file/remove', FileRemoveHandler),
        (r'/file/([^/]+)/([^/]+)', FileHandler),
        (r'/.*', Http404),
        ], debug=_DEBUG)
    run_wsgi_app(application)

