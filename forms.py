"""
WTForms форми для валідації даних
"""
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, DecimalField, IntegerField, BooleanField, PasswordField, FileField
from wtforms.validators import DataRequired, Length, Email, Optional, NumberRange, ValidationError
from models import User, Device, City, Employee

class LoginForm(FlaskForm):
    """Форма входу"""
    username = StringField('Логін', validators=[DataRequired(message='Введіть логін'), Length(min=3, max=80)])
    password = PasswordField('Пароль', validators=[DataRequired(message='Введіть пароль'), Length(min=3)])

class DeviceForm(FlaskForm):
    """Форма для додавання/редагування пристрою"""
    name = StringField('Назва', validators=[DataRequired(message='Введіть назву пристрою'), Length(max=100)])
    type = SelectField('Тип', validators=[DataRequired(message='Виберіть тип пристрою')], choices=[
        ('Комп\'ютер', 'Комп\'ютер'),
        ('Ноутбук', 'Ноутбук'),
        ('Планшет', 'Планшет'),
        ('Телефон', 'Телефон'),
        ('Принтер', 'Принтер'),
        ('Сканер', 'Сканер'),
        ('Монітор', 'Монітор'),
        ('Клавіатура', 'Клавіатура'),
        ('Миша', 'Миша'),
        ('Інше', 'Інше')
    ])
    serial_number = StringField('Серійний номер', validators=[DataRequired(message='Введіть серійний номер'), Length(max=100)])
    location = StringField('Місцезнаходження', validators=[Optional(), Length(max=200)])
    status = SelectField('Статус', validators=[DataRequired()], choices=[
        ('В роботі', 'В роботі'),
        ('На ремонті', 'На ремонті'),
        ('Списано', 'Списано'),
        ('Резерв', 'Резерв')
    ])
    notes = TextAreaField('Примітки', validators=[Optional()])
    city_id = SelectField('Місто', validators=[DataRequired()], coerce=int)
    assigned_to_employee_id = SelectField('Призначено співробітнику', validators=[Optional()], coerce=int)
    last_maintenance = DateField('Останнє обслуговування', validators=[Optional()], format='%Y-%m-%d')
    maintenance_interval = IntegerField('Інтервал обслуговування (днів)', validators=[Optional(), NumberRange(min=1, max=3650)])
    purchase_price = DecimalField('Вартість покупки', validators=[Optional(), NumberRange(min=0)])
    purchase_date = DateField('Дата покупки', validators=[Optional()], format='%Y-%m-%d')
    depreciation_rate = DecimalField('Відсоток амортизації (%)', validators=[Optional(), NumberRange(min=0, max=100)])
    
    def validate_serial_number(self, field):
        """Перевірка унікальності серійного номера"""
        device = Device.query.filter_by(serial_number=field.data).first()
        if device and (not hasattr(self, 'device_id') or device.id != self.device_id):
            raise ValidationError('Пристрій з таким серійним номером вже існує')

class EmployeeForm(FlaskForm):
    """Форма для додавання/редагування співробітника"""
    first_name = StringField('Ім\'я', validators=[DataRequired(message='Введіть ім\'я'), Length(max=50)])
    last_name = StringField('Прізвище', validators=[DataRequired(message='Введіть прізвище'), Length(max=50)])
    middle_name = StringField('По батькові', validators=[Optional(), Length(max=50)])
    position = StringField('Посада', validators=[Optional(), Length(max=100)])
    department = StringField('Відділ', validators=[Optional(), Length(max=100)])
    phone = StringField('Телефон', validators=[Optional(), Length(max=20)])
    email = StringField('Email', validators=[Optional(), Email(message='Невірний формат email'), Length(max=100)])
    city_id = SelectField('Місто', validators=[DataRequired()], coerce=int)
    notes = TextAreaField('Примітки', validators=[Optional()])

class UserForm(FlaskForm):
    """Форма для додавання/редагування користувача"""
    username = StringField('Логін', validators=[DataRequired(message='Введіть логін'), Length(min=3, max=80)])
    password = PasswordField('Пароль', validators=[Optional(), Length(min=8, message='Пароль має бути мінімум 8 символів')])
    is_admin = BooleanField('Адміністратор')
    is_active = BooleanField('Активний', default=True)
    city_id = SelectField('Місто', validators=[DataRequired()], coerce=int)
    
    def validate_username(self, field):
        """Перевірка унікальності логіна"""
        user = User.query.filter_by(username=field.data).first()
        if user and (not hasattr(self, 'user_id') or user.id != self.user_id):
            raise ValidationError('Користувач з таким логіном вже існує')

class CityForm(FlaskForm):
    """Форма для додавання/редагування міста"""
    name = StringField('Назва міста', validators=[DataRequired(message='Введіть назву міста'), Length(max=100)])
    
    def validate_name(self, field):
        """Перевірка унікальності назви міста"""
        city = City.query.filter_by(name=field.data).first()
        if city and (not hasattr(self, 'city_id') or city.id != self.city_id):
            raise ValidationError('Місто з такою назвою вже існує')

class RepairExpenseForm(FlaskForm):
    """Форма для додавання витрат на ремонт"""
    amount = DecimalField('Сума', validators=[DataRequired(message='Введіть суму'), NumberRange(min=0)])
    description = StringField('Опис робіт', validators=[Optional(), Length(max=500)])
    repair_date = DateField('Дата ремонту', validators=[DataRequired(message='Введіть дату ремонту')], format='%Y-%m-%d')
    invoice_number = StringField('Номер накладної', validators=[Optional(), Length(max=100)])

class PhotoUploadForm(FlaskForm):
    """Форма для завантаження фото"""
    photo = FileField('Фото', validators=[DataRequired(message='Виберіть файл')])

