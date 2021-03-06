#!/usr/bin/env python

import SimpleHTTPServer, SocketServer, socket
import argparse, urllib, subprocess, json, sys
import playlist

bindAddr = ('0.0.0.0', 8000)
selfAddr = None

ffmpegPath = False
castVolume = 1
castMute = False
castActionQueue = []

castUUID = None
playList = playlist.Playlist()

class ChromeCast(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def do_POST(self):
		restURI = [x for x in self.path.split('/') if x]

		# add track to playlist
		if restURI == ['playlist']:
			if self.client_address[0] != '127.0.0.1':
				self.send_response(403)
				self.end_headers()
				self.wfile.write('use 127.0.0.1 when adding files')
				return

			global playList
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			track = self.rfile.read(int(self.headers.getheader('content-length')))
			item = playList.insert(track)
			self.wfile.write(json.dumps({'uuid': item.uuid}))
			return

		# set casting uuid
		if restURI[0:1] == ['streamuuid'] and len(restURI) == 2:
			global castUUID
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			castUUID = restURI[1]
			self.wfile.write(json.dumps({'uuid': castUUID}))
			return

		self.send_response(500)
		self.send_header('Content-Type', 'application/json')
		self.end_headers()
		self.wfile.write(json.dumps({'error': 'unsupported REST call'}))
		return

    def do_DELETE(self):
		global playList, castUUID
		restURI = [x for x in self.path.split('/') if x]

		# delete track from playlist
		if restURI == ['playlist']:
			if self.client_address[0] != '127.0.0.1':
				self.send_response(403)
				self.end_headers()
				self.wfile.write('use 127.0.0.1 when adding files')
				return

			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			track = self.rfile.read(int(self.headers.getheader('content-length')))
			status = playList.remove(track)
			self.wfile.write(json.dumps({'status': status}))

			# skip track if currently playing
			if track == castUUID:
				castActionQueue.append(json.dumps({'playback': 'load'}))
			return

		# delete casting uuid
		if restURI == ['streamuuid']:
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			castUUID = None
			self.wfile.write(json.dumps({'uuid': castUUID}))
			return

		self.send_response(500)
		self.send_header('Content-Type', 'application/json')
		self.end_headers()
		self.wfile.write(json.dumps({'error': 'unsupported REST call'}))
		return

    def do_HEAD(self):
		self.send_response(500)
		self.end_headers()
		return

    def do_GET(self):
		global castVolume, castMute
		global ffmpegPath
		global castUUID, playList
		restURI = [x for x in self.path.split('/') if x]

		# serve html pages
		if restURI == []:
			self.send_response(200)
			self.send_header('Content-Type', 'text/html')
			self.end_headers()
			self.copyfile(urllib.urlopen('mobile.html'), self.wfile)
			return

		if restURI == ['backend']:
			self.send_response(200)
			self.send_header('Content-Type', 'text/html')
			self.end_headers()
			self.copyfile(urllib.urlopen('backend.html'), self.wfile)
			return

		# retrive playlist
		if restURI == ['playlist']:
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			l = dict()
			l['tracks'] = [{'name': p.name, 'uuid': p.uuid} for p in playList.items]
			l['repeat'] = playList.repeat
			l['repeatall'] = playList.repeatall
			l['shuffle'] = playList.shuffle
			self.wfile.write(json.dumps(l))
			return

		# play a uuid
		if restURI[0:1] == ['play'] and len(restURI) == 2:
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			uuid = restURI[1]
			self.wfile.write(json.dumps({'uuid': uuid}))
			castActionQueue.append(json.dumps({'playback': 'load', 'uuid': uuid}))
			return

		# next respects repeat
		if restURI[0:1] == ['next']:
			try:
				track = playList.nexttrack(restURI[1] if len(restURI) > 1 else castUUID)
				self.send_response(200)
				self.send_header('Content-Type', 'application/json')
				self.end_headers()
				if not track:
					self.wfile.write(json.dumps({'playback': 'stop'}))
					castActionQueue.append(json.dumps({'playback': 'stop'}))
					return
				self.wfile.write(json.dumps({'uuid': track.uuid}))
				castActionQueue.append(json.dumps({'playback': 'load', 'uuid': track.uuid}))
			except IndexError:
				self.send_response(404)
				self.send_header('Content-Type', 'application/json')
				self.end_headers()
				self.wfile.write(json.dumps({'error': 'empty playlist'}))
			return

		# repeat current uuid on /next
		if restURI[0:2] == ['set', 'repeat'] and len(restURI) == 3:
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			playList.repeat = restURI[2] == '1'
			self.wfile.write(json.dumps({'repeat': playList.repeat}))
			return

		if restURI[0:2] == ['set', 'repeatall'] and len(restURI) == 3:
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			playList.repeatall = restURI[2] == '1'
			self.wfile.write(json.dumps({'repeatall': playList.repeatall}))
			return

		# shuffle on /next
		if restURI[0:2] == ['set', 'shuffle'] and len(restURI) == 3:
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			playList.shuffle = restURI[2] == '1'
			self.wfile.write(json.dumps({'shuffle': playList.shuffle}))
			return

		# volume control
		if restURI[0:2] == ['set', 'volume'] and len(restURI) == 3:
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			castVolume = float(restURI[2])
			self.wfile.write(json.dumps({'volume': castVolume}))
			castActionQueue.append(json.dumps({'volume': castVolume}))
			return

		if restURI[0:2] == ['set', 'mute'] and len(restURI) == 3:
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			castMute = restURI[2] == '1'
			self.wfile.write(json.dumps({'mute': castMute}))
			castActionQueue.append(json.dumps({'mute': castMute}))
			return

		# playback control
		if restURI == ['pause'] or restURI == ['resume'] or restURI == ['stop']:
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			self.wfile.write(json.dumps({'playback': restURI[0]}))
			castActionQueue.append(json.dumps({'playback': restURI[0]}))
			return

		# get current casting UUID
		if restURI == ['streamuuid']:
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			self.wfile.write(json.dumps({'uuid': castUUID}))
			return

		# get stream info like duration
		if restURI[0:1] == ['streaminfo'] and len(restURI) == 2:
			track = playList.gettrack(restURI[1])
			if not track:
				self.send_response(404)
				self.send_header('Content-Type', 'application/json')
				self.end_headers()
				self.wfile.write(json.dumps({'error': 'uuid not in playlist'}))
				return

			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()

			ffmpeg = [
						ffmpegPath,
						'-i', track.path
					]

			# more stream info
			p = subprocess.Popen(ffmpeg, shell=False, stdin=None, stderr=subprocess.PIPE, bufsize=0)
			l = [s for s in p.communicate()[1].split('\n') if 'Duration' in s]
			if len(l):
				l = [[x.strip().lower() for x in s.strip().split(':', 1)] for s in l[0].split(',')]
			l = dict(l)
			l['duration'] = sum([a * b for a, b in zip([3600, 60, 1], map(int, l['duration'].split('.')[0].split(':')))])
			l['name'] = track.name
			l['path'] = track.path
			l['uuid'] = track.uuid
			l['streamurl'] = 'http://' + selfAddr + ':' + str(bindAddr[1]) + '/stream/'
			self.wfile.write(json.dumps(l))
			return

		# stream a uuid
		if restURI[0:1] == ['stream'] and len(restURI) == 2:
			track = playList.gettrack(restURI[1])
			if not track:
				self.send_response(404)
				self.send_header('Content-Type', 'application/json')
				self.end_headers()
				self.wfile.write(json.dumps({'error': 'uuid not in playlist'}))
				return

			self.send_response(200)
			self.send_header('Content-Type', 'video/x-matroska')
			self.end_headers()

			# add support for subtitles...
			ffmpeg = [
						ffmpegPath,
						'-y',
						'-i', track.path,
						'-vcodec', 'copy',
						'-acodec', 'aac',
						'-strict', '-2',
						'-movflags', 'faststart',
						'-f', 'matroska',
						'-'
					]

			null = open('/dev/null', 'w')
			p = subprocess.Popen(ffmpeg, shell=False, stdin=None, stderr=null, stdout=subprocess.PIPE, bufsize=0)
			byte = p.stdout.read(1024 * 1024)
			while byte:
					try:
						self.wfile.write(byte)
						self.wfile.flush()
					except:
						return
					byte = p.stdout.read(1024 * 1024)
			return

		# pop action from queue
		if restURI == ['streamqueue']:
			self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.end_headers()
			if len(castActionQueue) == 0:
				self.wfile.write(json.dumps({}))
			else:
				self.wfile.write(castActionQueue.pop(0))
			return

		self.send_response(500)
		self.send_header('Content-Type', 'application/json')
		self.end_headers()
		self.wfile.write(json.dumps({'error': 'unsupported REST call'}))
		return

class FastrebindServer(SocketServer.ThreadingTCPServer):
    def server_bind(self):
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.socket.bind(self.server_address)

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('--lan-ip', help='LAN address (on the same LAN as your Chromecast)')
	parser.add_argument('--ffmpeg', help='Path to ffmpeg')
	args = parser.parse_args()

	# Try to find ffmpeg in $PATH or $PWD
	if not args.ffmpeg:
		p = subprocess.Popen(['which', 'ffmpeg', './ffmpeg'], stdout=subprocess.PIPE)
		ffmpegPath = p.communicate()[0].split('\n')[0]
		if not ffmpegPath:
			print "Couldn't find 'ffmpeg' in $PATH or $PWD. https://www.ffmpeg.org/download.html"
			sys.exit(1)
	else:
		ffmpegPath = args.ffmpeg

	# Try to find
	if not args.lan_ip:
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			s.connect(('example.com', 80))
			selfAddr = s.getsockname()[0]
			s.close()
		except socket.error:
			print "Couldn't find your LAN address (on the same LAN as your Chromecast), use --lan-ip 1.1.1.1"
			sys.exit(1)
	else:
		selfAddr = args.lan_ip

	# Start server
	httpd = FastrebindServer(bindAddr, ChromeCast)
	try:
		print 'Ready to CastAway'
		print
		print 'Google Chromecast: http://127.0.0.1:' + str(bindAddr[1]) + '/backend'
		print 'Playlist and SDK:  http://' + selfAddr + ':' + str(bindAddr[1])
		print
		httpd.serve_forever()
	except KeyboardInterrupt:
		castActionQueue.append(json.dumps({'playback': 'stop'}))
		try:
			print 'Stopping casting...'
			while len(castActionQueue):
				httpd.handle_request();
		except KeyboardInterrupt:
			pass
		httpd.socket.close()
