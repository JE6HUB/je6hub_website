import re

# Read extracted_home.html
content = open('extracted_home.html').read()

# Make the hero section a liquid-glass-root
hero_pattern = re.compile(r'(<section class="jh-section jh-reveal)"( style="padding-top: 100px; padding-bottom: 60px;">)')
content = hero_pattern.sub(r'\1 liquid-glass-root"\2\n        <!-- Background element for glass to refract -->\n        <div style="position: absolute; inset: 0; background: radial-gradient(circle at 50% 0%, rgba(0,122,255,0.15) 0%, transparent 60%); z-index: -1;"></div>', content)

# Modify buttons to have liquid-glass-btn and .label span
btn1_pattern = re.compile(r'<a href="#work" class="jh-btn jh-btn-primary">([^<]+)</a>')
content = btn1_pattern.sub(r'<a href="#work" class="jh-btn jh-btn-primary mt-4 mx-2 liquid-glass-btn" style="display: inline-flex;" data-config=\'{"button":true, "cornerRadius":24, "blurAmount":0.4, "tint":"rgba(255, 255, 255, 0.15)"}\'><span class="label">\1</span></a>', content)

btn2_pattern = re.compile(r'<a href="{% url \'core:contact\' %}" class="jh-btn jh-btn-outline">([^<]+)<span class="material-symbols-outlined ms-2" style="font-size:18px;">arrow_forward</span></a>')
content = btn2_pattern.sub(r'<a href="{% url \'core:contact\' %}" class="jh-btn jh-btn-outline mt-4 mx-2 liquid-glass-btn" style="display: inline-flex;" data-config=\'{"button":true, "cornerRadius":24, "blurAmount":0.4, "tint":"rgba(255, 255, 255, 0.1)"}\'><span class="label d-flex align-items-center">\1<span class="material-symbols-outlined ms-2" style="font-size:18px;">arrow_forward</span></span></a>', content)

# Write to home.html
open('my_website/core/templates/core/home.html', 'w').write(content)
