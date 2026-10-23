-- v25 -> v26: el indicador guarda para qué funcionario se calculó (migración planning/0002_indicator_officer).
-- Solo hace falta si la base se actualiza a mano; con `deploy/actualizar.sh` la migración lo hace sola.
-- La columna admite NULL: los indicadores anteriores (sin funcionario) siguen válidos.
ALTER TABLE `planning_indicator`
  ADD COLUMN `officer_id` bigint NULL,
  ADD KEY `planning_indicator_officer_id_idx` (`officer_id`),
  ADD CONSTRAINT `planning_indicator_officer_id_fk`
    FOREIGN KEY (`officer_id`) REFERENCES `organization_officer` (`id`);
