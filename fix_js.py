import re

content = open('my_website/templates/base.html').read()
new_content = content.replace(
    'document.addEventListener("DOMContentLoaded", async () => {',
    'const initGlass = async () => {'
).replace(
    '});\n    </script>',
    '};\n        if (document.readyState === "loading") {\n            document.addEventListener("DOMContentLoaded", initGlass);\n        } else {\n            initGlass();\n        }\n    </script>'
)

open('my_website/templates/base.html', 'w').write(new_content)
