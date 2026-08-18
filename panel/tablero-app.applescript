-- Tablero.app — abre el tablero del escritorio con doble clic.
-- Arranca el servidor local si no está corriendo, espera a que responda y abre el navegador.
on run
	set laURL to "http://127.0.0.1:7373/"
	set elScript to (POSIX path of (path to home folder)) & ".panel/tablero.py"

	if servidorVivo() then
		-- Ya está arrancado: directo a la versión con botones.
		do shell script "/usr/bin/open " & quoted form of laURL
		return
	end if

	try
		do shell script "/usr/bin/nohup /usr/bin/python3 " & quoted form of elScript & " > /tmp/tablero.log 2>&1 &"
	on error laFalla
		display alert "No se pudo arrancar el tablero" message laFalla as critical
		return
	end try

	-- Abrimos ya la última foto guardada para no dejarte esperando en blanco:
	-- esa página sondea sola al servidor y salta a la versión viva cuando arranca (~15 s).
	set laFoto to (POSIX path of (path to home folder)) & ".panel/TABLERO.html"
	try
		do shell script "/usr/bin/open " & quoted form of laFoto
	on error
		display notification "Arrancando, unos segundos…" with title "Tablero"
	end try
end run

on servidorVivo()
	try
		do shell script "/usr/bin/curl -s -o /dev/null --max-time 2 http://127.0.0.1:7373/"
		return true
	on error
		return false
	end try
end servidorVivo
