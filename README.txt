Appointment site.

Models::

Appointment()

Appointment is the model for an appointment. As attributes it has:
  + description: A description about the appointment (eg. where, when, why?, etc).
  + invitee_list: The invitee list. It contains the e-mail address of all invitees.
  + date_list: A list of proposed dates for the appointment.
  + name: Name of person who is calling people for the appointment.
  + email: E-mail of person who is calling people for the appointment.


Invite()

Invitee is an invite model. When an appointment is created, an invite is created for each invitee on each date, including the appointment creator.
Eg. On appointment created by test@example.com with dates 2010-06-28, 2010-06-29, inviting test2@example.com and test3@example.com wil create six Invite instaqnces: one fot test2@example.com on 2010-06-28, one for test2@example.com on 2010-06-29, one for test3@example.com on 2010-06-28 and so on.
It has the folowing attributes:
  + email: Invitee's e-mail address.
  + date: Proposed date for the appointment.
  + status: Invitee availability for the appointment (yes, maybe, no).
  + appointment: The invite appointment.


Photo()

Photo is a storage model for a picture. Its attributes are:
  + user: The picture owner
  + blb_info: The picture itself
  + comment: A comment about the picture
  + public: Allow other people to see the picture
  + rotate: The picture rotation to display (0, 90, 180, 270)


File()

File is a storage model for all files that are not pictures. Its attributes are:
  + user: The file owner
  + blob_info: The file istself
  + comment: A comment about the file
  + public: Allow other people to download the file


Request Handlers::

When you call an url, eg. http://host.com/profile, the '/profile' part is mapped to a http request handler. In this application, except for file upload/download, all http request handlres inherite from BaseRequestHandler, a basic http request handler, that provides a template generator with some context variables, such current user, request parameters, etc.
For every request handler that inherites from BaseRequestHandler is implemented the methods get(), for GET http requests and post() for POST http requests.

Methods:
  + genereate(template_name, template_values): Render 'template_name' passing 'template_values' as parameter using the Django Template System.
  + error(code): Generate an error message for a http error code.

