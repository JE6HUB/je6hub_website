# Check if base and home are properly formatted HTML files now.
with open('my_website/templates/base.html') as f:
    print("base.html length:", len(f.read()))
with open('my_website/core/templates/core/home.html') as f:
    print("home.html length:", len(f.read()))
