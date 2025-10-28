from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import io
import qrcode
from datetime import datetime

def generate_device_pdf(device):
    """Генерує PDF інвентарної картки для пристрою"""
    buffer = io.BytesIO()
    
    # Створюємо документ
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    # Елементи документу
    elements = []
    
    # Стилі
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#343a40'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#495057'),
        spaceAfter=12
    )
    
    # Заголовок
    title = Paragraph("ІНВЕНТАРНА КАРТКА ОБЛАДНАННЯ", title_style)
    elements.append(title)
    elements.append(Spacer(1, 0.5*cm))
    
    # Генеруємо QR код
    qr_data = f"""ID: {device.id}
Назва: {device.name}
Інв. номер: {device.inventory_number}
S/N: {device.serial_number}"""
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Зберігаємо QR код в буфер
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)
    
    # Додаємо QR код
    qr_image = Image(qr_buffer, width=4*cm, height=4*cm)
    
    # Таблиця з основною інформацією
    data = [
        ['Інвентарний номер:', device.inventory_number or ''],
        ['Назва:', device.name or ''],
        ['Тип:', device.type or ''],
        ['Серійний номер:', device.serial_number or ''],
        ['Місце розташування:', device.location or ''],
        ['Статус:', device.status or ''],
        ['Місто:', device.city.name if device.city else ''],
        ['Дата додавання:', device.created_at.strftime('%d.%m.%Y') if device.created_at else ''],
    ]
    
    # Додаємо інформацію про обслуговування, якщо є
    if device.last_maintenance:
        data.append(['Останнє обслуговування:', device.last_maintenance.strftime('%d.%m.%Y')])
    if device.next_maintenance:
        data.append(['Наступне обслуговування:', device.next_maintenance.strftime('%d.%m.%Y')])
    if device.maintenance_interval:
        data.append(['Інтервал обслуговування (днів):', str(device.maintenance_interval)])
    
    # Створюємо таблицю
    t = Table(data, colWidths=[6*cm, 10*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e9ecef')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    # Таблиця з QR кодом і основною інформацією
    main_table = Table([[t, qr_image]], colWidths=[12*cm, 5*cm])
    main_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
    ]))
    
    elements.append(main_table)
    elements.append(Spacer(1, 1*cm))
    
    # Примітки
    if device.notes:
        notes_heading = Paragraph("Примітки:", heading_style)
        elements.append(notes_heading)
        notes_text = Paragraph(device.notes.replace('\n', '<br/>'), styles['Normal'])
        elements.append(notes_text)
        elements.append(Spacer(1, 1*cm))
    
    # Футер
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    footer = Paragraph(
        f"Згенеровано: {datetime.now().strftime('%d.%m.%Y %H:%M')} | Система інвентаризації обладнання",
        footer_style
    )
    elements.append(Spacer(1, 2*cm))
    elements.append(footer)
    
    # Будуємо PDF
    doc.build(elements)
    
    buffer.seek(0)
    return buffer

def generate_bulk_devices_pdf(devices):
    """Генерує PDF з декількома інвентарними картками"""
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#343a40'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    # Заголовок
    title = Paragraph("РЕЄСТР ОБЛАДНАННЯ", title_style)
    elements.append(title)
    elements.append(Spacer(1, 0.5*cm))
    
    # Створюємо таблицю з пристроями
    table_data = [['№', 'Інв. номер', 'Назва', 'Тип', 'S/N', 'Місце', 'Статус']]
    
    for idx, device in enumerate(devices, 1):
        table_data.append([
            str(idx),
            device.inventory_number or '',
            device.name or '',
            device.type or '',
            device.serial_number or '',
            device.location or '',
            device.status or ''
        ])
    
    t = Table(table_data, colWidths=[1*cm, 3*cm, 4*cm, 3*cm, 3*cm, 3*cm, 2*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#343a40')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
    ]))
    
    elements.append(t)
    elements.append(Spacer(1, 1*cm))
    
    # Футер
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    footer = Paragraph(
        f"Згенеровано: {datetime.now().strftime('%d.%m.%Y %H:%M')} | Всього пристроїв: {len(devices)}",
        footer_style
    )
    elements.append(footer)
    
    doc.build(elements)
    
    buffer.seek(0)
    return buffer

