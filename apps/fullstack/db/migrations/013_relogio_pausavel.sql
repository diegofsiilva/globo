-- 013_relogio_pausavel.sql
--
-- Congela o relogio virtual junto com o encerramento de uma execucao.
--
-- Antes desta migration, marcar sim.run como `paused` ou `done` nao alterava
-- sim.clock. Como sim.now() deriva do relogio de parede, o tempo continuava
-- avancando mesmo com o servico do simulador em desired_count = 0. Alem de a
-- API sair da janela do dump, isso fazia o lag_sim crescer sem haver produtor.

CREATE FUNCTION sim.pause_clock(p_now timestamptz DEFAULT NULL)
RETURNS timestamptz
LANGUAGE plpgsql AS $$
DECLARE
  v_now timestamptz;
BEGIN
  UPDATE sim.clock
     SET sim_now = COALESCE(
           p_now,
           sim_now + (now() - anchor_wall) * speed
         ),
         speed = 0,
         anchor_wall = now(),
         updated_at = now()
   WHERE id = 1
  RETURNING sim_now INTO v_now;

  RETURN v_now;
END
$$;

COMMENT ON FUNCTION sim.pause_clock(timestamptz) IS
  'Congela o relogio no instante informado ou no sim.now() corrente';

CREATE FUNCTION sim.close_run(
  p_run_id bigint,
  p_status text,
  p_now timestamptz DEFAULT NULL
)
RETURNS timestamptz
LANGUAGE plpgsql AS $$
DECLARE
  v_now timestamptz;
BEGIN
  IF p_status NOT IN ('paused', 'done') THEN
    RAISE EXCEPTION 'status final invalido: %', p_status
      USING ERRCODE = 'check_violation';
  END IF;

  UPDATE sim.run
     SET status = p_status
   WHERE run_id = p_run_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'sim.run inexistente: %', p_run_id
      USING ERRCODE = 'no_data_found';
  END IF;

  v_now := sim.pause_clock(p_now);
  RETURN v_now;
END
$$;

COMMENT ON FUNCTION sim.close_run(bigint, text, timestamptz) IS
  'Encerra a execucao e congela sim.clock na mesma transacao';

-- Recupera bancos que ja sofreram o defeito. Se nao ha execucao running, o
-- relogio nao pode continuar andando. Quando ele ja ultrapassou o fim das
-- execucoes conhecidas, ancora no maior t1 para manter o dashboard dentro do
-- recorte do dump em vez de deixa-lo meses no futuro.
DO $$
DECLARE
  v_recovery_now timestamptz;
BEGIN
  IF EXISTS (SELECT 1 FROM sim.run)
     AND NOT EXISTS (SELECT 1 FROM sim.run WHERE status = 'running')
     AND EXISTS (SELECT 1 FROM sim.clock WHERE id = 1 AND speed <> 0) THEN
    SELECT LEAST(sim.now(), max(t1))
      INTO v_recovery_now
      FROM sim.run;
    PERFORM sim.pause_clock(v_recovery_now);
  END IF;
END
$$;
