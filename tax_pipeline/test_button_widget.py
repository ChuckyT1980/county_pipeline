import fitz

doc = fitz.open()
page = doc.new_page()
page.insert_text(fitz.Point(50, 100), "Test with button widget:", fontsize=14)

widget = fitz.Widget()
widget.rect = fitz.Rect(50, 120, 300, 150)
widget.border_color = (0, 0, 1)
widget.border_width = 1
widget.fill_color = (0.8, 0.85, 1)
widget.script = "app.launchURL('https://common1.mptsweb.com/MBC/tehama/tax/main/037120008000/2025/0000', true)"
widget.field_type = fitz.PDF_WIDGET_TYPE_BUTTON
widget.field_name = "assessor_link_1"
widget.button_caption = "Open Assessor Page"
page.add_widget(widget)

out = "test_button.pdf"
doc.save(out)
doc.close()
print(f"Created {out}")
