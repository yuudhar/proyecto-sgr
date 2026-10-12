"""Catálogo y generador del registro de pruebas (A3 · «Registro de cada prueba funcional»).

El registro se arma a partir de las pruebas automáticas reales del proyecto: ``catalogo.py`` dice a qué
requisito y módulo pertenece cada clase de pruebas, y los archivos ``esperado_*.py`` traen, en español, qué
debe ocurrir en cada prueba. ``python manage.py exportar_registro_pruebas`` ejecuta la suite y escribe el
registro en ``docs/pruebas/``.
"""
