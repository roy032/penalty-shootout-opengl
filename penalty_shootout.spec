# PyInstaller recipe for a Windows build that needs no Python install.
#
#   vcpkg install freeglut:x64-windows
#   pip install -r requirements.txt pyinstaller
#   pyinstaller --noconfirm penalty_shootout.spec
#
# The result is dist/PenaltyShootout/PenaltyShootout.exe. PyOpenGL looks for
# GLUT as freeglut64.vc14.dll in its OpenGL/DLLS folder, so the vcpkg DLL is
# copied in under that name. Set FREEGLUT_DLL if vcpkg lives somewhere else.
import os
import shutil

root = os.environ.get('VCPKG_INSTALLATION_ROOT', r'C:\vcpkg')
glut = os.environ.get('FREEGLUT_DLL', os.path.join(root, 'installed', 'x64-windows', 'bin', 'freeglut.dll'))
binaries = []
if os.path.exists(glut):
    os.makedirs('build', exist_ok=True)
    renamed = os.path.join('build', 'freeglut64.vc14.dll')
    shutil.copyfile(glut, renamed)
    binaries.append((renamed, os.path.join('OpenGL', 'DLLS')))
else:
    print(f'WARNING: {glut} not found: the build will need freeglut installed separately')

a = Analysis(
    ['penalty_shootout.py'],
    binaries=binaries,
    hiddenimports=[
        'OpenGL.platform.win32', 'OpenGL.arrays.ctypesarrays', 'OpenGL.arrays.ctypesparameters',
        'OpenGL.arrays.ctypespointers', 'OpenGL.arrays.lists', 'OpenGL.arrays.numbers', 'OpenGL.arrays.strings',
        'OpenGL.arrays.nones', 'OpenGL.arrays.buffers', 'OpenGL.WGL.EXT.swap_control',
        'PIL.ImageFont', 'PIL.ImageDraw',
        'pyttsx3.drivers', 'pyttsx3.drivers.sapi5',
    ],
    excludes=['tkinter', 'pytest'],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PenaltyShootout', console=False)
coll = COLLECT(exe, a.binaries, a.datas, name='PenaltyShootout')
