# Tornillos, Tuercas, Agujeros y Roscas

Complemento para FreeCAD 1.1.3. Añade tres accesos a la barra y al panel **Tareas** de **Part Design**.

- **Tornillo** crea y edita tornillos paramétricos.
- **Tuerca** crea y edita tuercas y tubos roscados.
- **Agujeros y Roscas** abre el editor de agujeros con posición y orientación propias. En un Cuerpo vacío, **OK** guarda el agujero pendiente y editable. Al añadir material al Cuerpo, el agujero se activa y el corte se vuelve a calcular con los siguientes añadidos.

Los accesos y las operaciones nuevas se llaman **Tornillo**, **Tuerca** y **Agujeros y Roscas**. Si el documento tiene un único **Cuerpo**, las herramientas lo usan directamente. Si hay varios, activa o selecciona uno en el árbol. El croquis de referencia del agujero se genera internamente a partir del origen del Cuerpo.

## Instalación manual

1. Cierra FreeCAD.
2. Descomprime el ZIP en el directorio `Mod` de usuario. Para localizarlo, puedes consultar `App.getUserAppDataDir()` en la consola Python de FreeCAD antes de cerrarlo.
3. Comprueba que `Mod/tornillos-tuercas-agujeros-y-roscas/InitGui.py` existe. Abre FreeCAD, entra en **Part Design** y abre o crea un documento con un **Cuerpo**.

## Prueba del repositorio

La macro `tests/PruebaIndependiente.FCMacro` comprueba la apertura, confirmación y reedición en documentos nuevos. Ejecútala con el complemento instalado en un perfil temporal iniciado con `--user-cfg`. La prueba escribe el resultado junto a ese archivo de configuración.
