git add core/ app.py app_gui.py "Buscar Santamaria Noticias GUI.spec" buscador_noticias_legacy.py requirements.txt
git commit -m "BNAS 5.0 Modernization: Async Core, modularization, Streamlit integration, CustomTkinter separation"
git push
pyinstaller --noconfirm "Buscar Santamaria Noticias GUI.spec"
