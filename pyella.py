import os
import urllib2, urllib
import re
import urlparse
try:
    from hashlib import md5
except ImportError:
    from md5 import md5

from xml.dom import minidom

__name__ = 'pyella'
__version__ = '0.6.9'
__doc__ = 'A python interface to BMAT web service (API)'
__author__ = 'Pau Capella, Oscar Celma' #inspired by pylastfm.py
__license__ = 'GPL'
__maintainer__ = 'Oscar Celma'
__email__ = 'ocelma@bmat.com'
__status__ = 'Beta'

HOST_NAME = 'ella.bmat.ws'
USERNAME = 'musichackday'
PASSWORD = 'mhdbcn2010_'

__cache_dir = None
__cache_enabled = False

class ServiceException(Exception):
    """Exception related to the web service."""
    
    def __init__(self, type, message):
        self._type = type
        self._message = message
    
    def __str__(self):
        return self._type + ': ' + self._message
    
    def get_message(self):
        return self._message

    def get_type(self):
        return self._type

class _Request(object):
    """Representing an abstract web service operation."""

    def __init__(self, method_name, params, collection, ellaws):
        self.params = params
        self.collection = collection
        self.method = method_name
        self.ellaws = ellaws

    def _download_response(self):
        """Returns a response"""
        data = []
        for name in self.params.keys():
            data.append('='.join((name, urllib.quote_plus(self.params[name].replace('&amp;', '&').encode('utf8')))))

        data = '&'.join(data)

        url = self.ellaws
        parsed_url = urlparse.urlparse(url)
        if not parsed_url.scheme:
            url = "http://" + url
        if self.collection:
            if not url.endswith('/'):
                url +='/'
            url += 'collections/' + self.collection
        url += self.method + '?' + data

        #print url

        passmanager = urllib2.HTTPPasswordMgrWithDefaultRealm()
        passmanager.add_password(None, url, USERNAME, PASSWORD)
        authhandler = urllib2.HTTPBasicAuthHandler(passmanager)
        opener = urllib2.build_opener(authhandler)
        urllib2.install_opener(opener)

        request = urllib2.Request(url)
        response = urllib2.urlopen(request)
        return response.read() 

    def execute(self, cacheable=False):
        try:
            if is_caching_enabled() and cacheable:
                response = self._get_cached_response()
            else:
                response = self._download_response()
            return minidom.parseString(response)
        except urllib2.HTTPError, e:
            raise self._get_error(e.fp.read())

    def _get_cache_key(self):
        """Cache key""" 
        keys = self.params.keys()[:]
        keys.sort()

        if self.collection:
            string = self.collection + self.method
        else:
            string = self.method

        for name in keys:
            string += name
            string += self.params[name]
        return get_md5(string)

    def _is_cached(self):
        """Returns True if the request is available in the cache."""
        return os.path.exists(os.path.join(_get_cache_dir(), self._get_cache_key()))

    def _get_cached_response(self):
        """Returns a file object of the cached response."""
        if not self._is_cached():
            response = self._download_response()
            response_file = open(os.path.join(_get_cache_dir(), self._get_cache_key()), "w")
            response_file.write(response)
            response_file.close()
        return open(os.path.join(_get_cache_dir(), self._get_cache_key()), "r").read()

    def _get_error(self, text):
        doc = minidom.parseString(text)
        message = _extract(doc, 'message')
        type = _extract(doc, 'type')
        if type and message: return ServiceException(type, message)
        raise

class _BaseObject(object):
    """An abstract webservices object."""
        
    def __init__(self, collection, ellaws):                
        self.collection = collection
        self.ellaws = ellaws
    
    def _request(self, method_name , cacheable = False, params = None):
        if not params:
            params = self._get_params()    
        return _Request(method_name, params, self.collection, self.ellaws).execute(cacheable)
    
    def _get_params(self):
        return dict()

class Artist(_BaseObject):
    """ A Bmat artist """
    def __init__(self, id, collection, ellaws=HOST_NAME):
        _BaseObject.__init__(self, collection, ellaws)

        self.name = None
        self.id = id
        self._method = '/artists/' + self.id + '.xml'

        self._mbid = None
        self._links = None
        self._tags = None
        self._releases = None
        self._tracks = None
        self._similar_artists = None
        self._popularity = None
        self._location = None
        self._lat = None
        self._lng = None
        self._recommend = None
        self._decades = None

        self._metadata_links = ['official_homepage_artist_url','wikipedia_artist_url','lastfm_artist_url','myspace_artist_url','spotify_artist_url','itms_artist_url','discogs_artist_url']
        self._metadata = 'artist,name,artist_popularity,artist_location,recommendable,artist_decades1,artist_decades2,artist_latlng,musicbrainz_artist_id,'
        self._metadata += ','.join(self._metadata_links)

        self._vector_cf = None
        self._vector_ct = None
        self._vector_cb = None

        self._xml = None
    
    def __repr__(self):
       return self.get_name().encode('utf8')

    def __eq__(self, other):
        return self.get_id() == other.get_id()

    def __ne__(self, other):
        return self.get_id() != other.get_id()

    def get_name(self):
        """ Returns the name of the artist """
        if self.name is None:
            self.name = ''
            try:
                if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
                self.name = _extract(self._xml, 'artist', 1) or ''
            except:
                return self.name
        return self.name

    def set_name(self, name) :
        self.name = name

    def get_id(self):
        """ Returns the bmat id """
        return self.id

    def get_links(self):
        """ Returns the external links of an artist """
        if self._links is None:
            self._links = []
            try :
                if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
                self._links = []
                for link in self._metadata_links :
                    self._links.append((link, _extract(self._xml, link)))
            except:
                return self._links
        return self._links

    def get_tags(self, tag_type='style', tag_weight=0.70, limit=4):
        """ Returns the tag cloud of an artist """
        if not self.has_recommendations(): 
            return None

        if self._tags is None:
            self._tags = []
            limit = 100
            method = '/artists/%s/similar/collections/tags/tags.xml' % self.id
            xml = self._request(method, True, {'limit': str(limit), 'filter': 'tag_type:%s' % tag_type})
            for tag in xml.getElementsByTagName('tag') :
                relevance = _extract(tag, 'relevance')
                if not relevance: 
                    continue
                relevance = float(relevance)
                if relevance < tag_weight: 
                    break
                self._tags.append( (relevance, tag.getAttribute('id')) )
        if self._tags : self._tags.sort(reverse=True)
        return self._tags[:limit]

    def get_releases(self):
        """ Returns the albums of an artist """
        if self._releases is not None: return self._releases

        list = []
        method = '/artists/' + self.id + '/releases.xml'
        metadata =  'release,release_small_image,release_label,'
        metadata_links = ['spotify_release_url','amazon_release_url','itms_release_url','rhapsody_release_url','emusic_release_url','limewire_release_url','trackitdown_release_url','juno_release_url', 'rateyourmusic_release_url','metacritic_release_url','pitchfork_release_url','bbc_co_uk_release_url','rollingstone_release_url','cloudspeakers_url']
        metadata = metadata + ','.join(metadata_links)

        xml = self._request(method, True, {'fetch_metadata': metadata})
        for node in xml.getElementsByTagName('release'):
            album_id = node.getAttribute('id') 
            if not album_id: continue
            album = Album(album_id, self.collection, self.ellaws)
            album.set_title(_extract(node, 'release'))
            album.set_artist(self)
            album.set_image(_extract(node, 'release_small_image'))
            album.set_label(_extract(node, 'release_label'))
            for link in metadata_links :
                album.set_link(link, _extract(node, link))
            if album.get_links() is None: album._links = None
            list.append(album)
        self._releases = list
        return self._releases

    def get_tracks(self):
        """ Returns the tracks of an artist """
        if self._tracks is not None: return self._tracks

        list = []
        method = '/artists/' + self.id + '/tracks.xml'
        metadata = 'track,artist_service_id,artist,release_service_id,release,location,year,genre,track_popularity,track_small_image,recommendable,musicbrainz_track_id,spotify_track_uri,'
        metadata_links = ['spotify_track_url', 'grooveshark_track_url', 'amazon_track_url','itms_track_url','hypem_track_url','musicbrainz_track_url']
        metadata = metadata + ','.join(metadata_links)

        xml = self._request(method, True, {'fetch_metadata': metadata})
        for node in xml.getElementsByTagName('track'):
            track_id = node.getAttribute('id') 
            if not track_id: continue
            track = Track(track_id, self, self.collection, self.ellaws)
            track.set_title(_extract(node, 'track'))
            track.set_audio(_extract(node, 'location'))

            track.set_artist(self)
            track.set_artist_name(self.get_name())
            track.set_artist_id(self.get_id())
            track.set_mbid(_extract(node, 'musicbrainz_track_id'))

            album_id = _extract(node, 'release_service_id')
            if album_id:
                album = Album(album_id, self.collection, self.ellaws)
                album.set_title(_extract(node, 'release'))
                album.set_artist(self)

                track.set_album(album)
                track.set_album_title(album.get_title())
                track.set_album_id(album.get_id())
            else :
                track.set_album_title('')
                track.set_album_id('')

            popularity = _extract(node, 'track_popularity')
            if not popularity:
                popularity = 0
            track.set_popularity(popularity)

            recommendable = _extract(node, 'recommendable')
            if not recommendable:
                recommendable = True
            track.set_recommend(recommendable)

            image = _extract(node, 'track_small_image')
            track.set_image(image)

            for link in metadata_links :
                track.set_link(link, _extract(node, link))
            if track.get_links() is None: track._links = []
            list.append(track)
        self._tracks = list
        return self._tracks

    def get_similar(self):
        """ Returns the similar artists """
        if not self.has_recommendations(): 
            return None

        if self._similar_artists is not None: return self._similar_artists
        list = []
        method = '/artists/' + self.id + '/similar/artists.xml'
        xml = self._request(method, True, {'fetch_metadata': self._metadata})
        for node in xml.getElementsByTagName('artist'):
            artist_id = node.getAttribute('id') 
            if artist_id == self.id : continue
            if not artist_id: continue
            artist = Artist(artist_id, self.collection, self.ellaws)
            artist.set_name(_extract(node, 'name'))

            popularity = _extract(node, 'artist_popularity')
            if not popularity:
                popularity = 0
            artist.set_popularity(popularity)

            location = _extract(node, 'artist_location')
            if not location:
                location = ''
            artist.set_location(location)

            recommendable = _extract(node, 'recommendable')
            if not recommendable:
                recommendable = True
            artist.set_recommend(recommendable)

            list.append((artist, _extract(node, 'relevance')))
        self._similar_artists = list
        return self._similar_artists

    def get_mbid(self):
        """ Returns artist musicbrainz id """
        if self._mbid is None :
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self.set_mbid(_extract(self._xml, 'musicbrainz_artist_id'))
        return self._mbid

    def set_mbid(self, mbid):
        """ Sets artist mbid """
        if mbid is None: mbid = ''
        self._mbid = mbid

    def get_popularity(self):
        """ Returns artist popularity """
        if self._popularity is None :
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self.set_popularity(_extract(self._xml, 'artist_popularity'))
        return self._popularity

    def set_popularity(self, popularity):
        """ Sets artist popularity """
        if popularity is None: popularity = 0.0
        self._popularity = round(float(popularity), 2)

    def get_location(self):
        """ Returns artist location """
        if self._location is None :
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self.set_location(_extract(self._xml, 'artist_location'))
        return self._location

    def set_location(self, location):
        """ Sets artist location """
        if location is None: location = ''
        self._location = location

    def get_lat(self):
        """ Returns artist latitude """
        if self._lat is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self.set_lat(_extract(self._xml, 'artist_latlng').split(',')[0])
        return self._lat

    def set_lat(self, lat):
        """ Sets artist latitude """
        self._lat = lat

    def get_lng(self):
        """ Returns artist longitude """
        if self._lng is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self.set_lng(_extract(self._xml, 'artist_latlng').split(',')[1])
        return self._lng

    def set_lng(self, lng):
        """ Sets artist longitude """
        self._lng = lng

    def get_decades(self):
        """ Returns artist decades """
        if self._decades is None :
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self.set_decades(_extract(self._xml, 'artist_decades1'), _extract(self._xml, 'artist_decades2'))
        return self._decades

    def set_decades(self, decade1, decade2):
        """ Sets artist decades """
        if decade1 is None or decade1 == '':
            decade1 = ''
        if decade2 is None or decade2 == '':
            decade2 = ''
        self._decades = ( (decade1, decade2) )

    def has_recommendations(self):
        """ Returns whether we can get similar items or not, given this seed artist """
        if self._recommend is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            recommend = _extract(self._xml, 'recommendable')
            if not recommend: return True
            self._recommend = self.set_recommend(recommend)
        return self._recommend

    def set_recommend(self, recommend):
        if recommend is None: recommend = True
        if str(recommend).capitalize() == 'False': recommend = False
        self._recommend = recommend


class Album(_BaseObject):
    """ A Bmat album """
    def __init__(self, id, collection, ellaws=HOST_NAME):
        _BaseObject.__init__(self, collection, ellaws)
        
        self.artist = None
        self.name = None
        self.id = id
        self._method = '/releases/' + self.id + '.xml'
        self._image = None
        self._mbid = None

        self._links = None
        self._label = None
        self._tags = None
        self._tracks = None

        self._metadata_links = ['spotify_release_url','amazon_release_url','itms_release_url','rhapsody_release_url','emusic_release_url','limewire_release_url','trackitdown_release_url','juno_release_url','rateyourmusic_release_url','metacritic_release_url','pitchfork_release_url','bbc_co_uk_release_url','rollingstone_release_url','cloudspeakers_url']
        self._metadata = 'release,name,artist_service_id,release_small_image,release_label,musicbrainz_release_id,'
        self._metadata += ','.join(self._metadata_links)

        self._xml = None
    
    def __repr__(self):
       return self.get_title().encode('utf8')

    def __eq__(self, other):
        return self.get_id() == other.get_id()

    def __ne__(self, other):
        return self.get_id() != other.get_id()


    def get_title(self):
        """ Returns the name of the album """
        if self.name is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self.name = _extract(self._xml, 'release', 1)
        return self.name

    def set_title(self, name):
        if name is None: name = ''
        self.name = name

    def get_label(self):
        """ Returns the label of the album """
        if self._label is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self._label = _extract(self._xml, 'release_label')
        return self._label

    def set_label(self, label):
        if label is None: label = ''
        self._label = label

    def get_id(self):
        """ Returns the bmat id """
        return self.id

    def get_artist(self):
        """ Returns the associated Artist object """
        if not self.artist:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            artist_id = _extract(self._xml, 'artist_service_id')
            self.artist = Artist(artist_id, self.collection, self.ellaws)
        return self.artist

    def set_artist(self, artist):
        self.artist = artist

    def get_links(self):
        """ Returns the external links of an album """
        if self._links is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self._links = []
            for link in self._metadata_links :
                self._links.append((link, _extract(self._xml, link)))
        return self._links

    def set_link(self, service, link) :
        """ Sets an external link for the album """
        if not self._links :
            self._links = []
        self._links.append((service, link))

    def get_image(self):
        """ Returns Amazon image url """
        if self._image is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self._image = _extract(self._xml, 'release_small_image')
        return self._image

    def set_image(self, image):
        if image is None: 
            image = ''
        self._image = image

    def get_mbid(self):
        """ Returns album musicbrainz id """
        if self._mbid is None :
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self.set_mbid(_extract(self._xml, 'musicbrainz_release_id'))
        return self._mbid

    def set_mbid(self, mbid):
        """ Sets album mbid """
        if mbid is None: mbid = ''
        self._mbid = mbid


    def get_tracks(self):
        """ Returns the tracks of an album """
        if self._tracks is not None: return self._tracks

        list = []
        method = '/releases/' + self.id + '/tracks.xml'
        metadata = 'track,artist_service_id,artist,release_service_id,release,location,year,genre,track_popularity,track_small_image,recommendable,artist_decades1,artist_decades2,musicbrainz_track_id,'
        metadata_links = ['spotify_track_url', 'grooveshark_track_url', 'amazon_track_url','itms_track_url','hypem_track_url','musicbrainz_track_url']
        metadata = metadata + ','.join(metadata_links)

        xml = self._request(method, True, {'fetch_metadata': metadata})
        #Get artist info, is it's not set yet
        if self.artist is None:
            artist_id = _extract(xml, 'artist_service_id')
            self.artist = Artist(artist_id, self.collection, self.ellaws)
        for node in xml.getElementsByTagName('track'):
            track_id = node.getAttribute('id') 
            if not track_id: continue
            track = Track(track_id, self.artist, self.collection, self.ellaws)
            track.set_title(_extract(node, 'track'))
            track.set_audio(_extract(node, 'location'))
            track.set_album(self)
            track.set_album_title(self.get_title())
            track.set_album_id(self.get_id())
            track.set_mbid(_extract(node, 'musicbrainz_track_id'))
            popularity = _extract(node, 'track_popularity')
            if not popularity:
                popularity = 0
            track.set_popularity(popularity)

            recommendable = _extract(node, 'recommendable')
            if not recommendable:
                recommendable = True
            track.set_recommend(recommendable)

            image = _extract(node, 'track_small_image')
            track.set_image(image)

            if self.artist is not None:
                track.set_artist(self.artist)
                track.set_artist_name(self.artist.get_name())
                track.set_artist_id(self.artist.get_id())
            for link in metadata_links :
                track.set_link(link, _extract(node, link))
            if track.get_links() is None: track._links = []
            list.append(track)
        self._tracks = list
        return self._tracks

class Track(_BaseObject):
    """ A Bmat track. """
    def __init__(self, id, artist, collection, ellaws=HOST_NAME):
        _BaseObject.__init__(self, collection, ellaws)

        if isinstance(artist, Artist):
            self.artist = artist
        else:
            self.artist = None
        self.id = id
        self.title = None
        self.audio = None
        self._image = None
        self._mbid = None

        self.artist = None
        self._artist_id = None
        self._artist_name = None

        self.album = None
        self._album_id = None
        self._album_title = None
    
        self._similar_tracks = None
        self._links = None
        self._tags = None
        self._popularity = None

        self._lat = None
        self._lng = None

        self._recommend = None

        self._method = ''
        if self.id is not None:
            self._method = '/tracks/' + self.id + '.xml'

        self._metadata = 'track,name,artist_service_id,artist,release_service_id,release,location,year,genre,track_popularity,track_small_image,recommendable,spotify_track_uri,'
        self._metadata_links = ['spotify_track_url', 'grooveshark_track_url', 'amazon_track_url','itms_track_url','hypem_track_url','musicbrainz_track_url']
        self._metadata += ','.join(self._metadata_links)

        self._xml = None

    def __repr__(self):
        return self.get_artist_name().encode('utf8') + ' - ' + self.get_title().encode('utf8')

    def __eq__(self, other):
        return self.get_id() == other.get_id()

    def __ne__(self, other):
        return self.get_id() != other.get_id()

    def get_id(self):
        """ Returns the bmat id """
        return self.id

    def get_artist(self):
        """ Returns the associated Artist id """
        if not self.artist:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            artist_id = _extract(self._xml, 'artist_service_id')
            if not artist_id: return None
            self.artist = Artist(artist_id, self.collection, self.ellaws)
        return self.artist

    def set_artist(self, artist):
        """ Returns the album title where the track appears on """
        self.artist = artist

    def get_artist_id(self):
        """ Returns the associated Artist object """
        if self._artist_id is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            artist_id = _extract(self._xml, 'artist_service_id')
            if not artist_id: return None
            self._artist_id = artist_id
        return self._artist_id

    def set_artist_id(self, artist_id):
        """ Returns the album title where the track appears on """
        self._artist_id = artist_id

    def get_album(self):
        """ Returns the associated Album object """
        if not self.album:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            album_id = _extract(self._xml, 'release_service_id')
            if not album_id: return None
            self.album = Album(album_id, self.collection, self.ellaws)
        return self.album

    def set_album(self, album):
        self.album = album

    def get_album_id(self):
        """ Returns the associated Album id """
        if self._album_id is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            album_id = _extract(self._xml, 'release_service_id')
            if not album_id: return None
            self._album_id = album_id
        return self._album_id

    def set_album_id(self, album_id):
        self._album_id = album_id

    def has_recommendations(self):
        """ Returns whether we can get similar tracks, given this seed song """
        if self._recommend is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            recommend = _extract(self._xml, 'recommendable')
            if not recommend: return True
            self._recommend = self.set_recommend(recommend)
        return self._recommend and self.get_title()

    def set_recommend(self, recommend):
        if recommend is None: recommend = True
        if str(recommend).capitalize() == 'False': recommend = False
        self._recommend = recommend

    def get_title(self):
        """ Returns the track title """
        if self.title is None:
            #self.title = _extract(self._request(self._method, True, {'fetch_metadata':'track'}), 'track', 1)
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self.title = _extract(self._xml, 'name', 1)
            if not self.title:
                self.title = _extract(self._xml, 'track', 1)
        return self.title

    def set_title(self, title):
        self.title = title

    def get_full_title(self):
        return self.get_artist_name() + ' - ' + self.get_title()

    def get_album_title(self):
        """ Returns the album title where the track appears on """
        if self._album_title is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self._album_title = _extract(self._xml, 'release')
        return self._album_title

    def set_album_title(self, title):
        """ Returns the album title where the track appears on """
        self._album_title = title

    def get_artist_name(self):
        """ Returns the artist name of the track """
        if self._artist_name is None:
            if self.artist:
                self._artist_name = self.artist.get_name()
            if not self.artist and not self._xml:
                self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
                self._artist_name = _extract(self._xml, 'artist')
        return self._artist_name

    def set_artist_name(self, name):
        """ Returns the album title where the track appears on """
        self._artist_name = name

    def get_audio(self):
        """ Returns audio url """
        if self.audio is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self.audio = _extract(self._xml, 'location')
        return self.audio

    def set_audio(self, audio):
        self.audio = audio

    def get_image(self):
        """ Returns Amazon image url """
        if self._image is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self._image = _extract(self._xml, 'track_small_image')
        return self._image

    def set_image(self, image):
        if image is None: image = ''
        self._image = image

    def get_mbid(self):
        """ Returns track musicbrainz id """
        if self._mbid is None :
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self.set_mbid(_extract(self._xml, 'musicbrainz_track_id'))
        return self._mbid

    def set_mbid(self, mbid):
        """ Sets track mbid """
        if mbid is None: mbid = ''
        self._mbid = mbid

    def get_similar(self, limit=20, filter=None, collection_sim=None, seeds=None, threshold=None, similarity_type=None):
        """ Returns the similar track in collection_sim """
        #if self._similar_tracks is not None : return self._similar_tracks
        params = {}
        params['limit'] = str(limit)
        params['fetch_metadata'] = self._metadata

        #Add filters
        if filter:
            params['filter'] = ' AND '.join(filter)

        if self.id is not None:
            params['seeds'] = self.collection + ':track/' + self.id
        #Add other seeds
        if seeds :
            for key in seeds.keys():
                if params.has_key('seeds'):
                    params['seeds'] = params['seeds'] + ',' + seeds[key]['collection'] + ':' + seeds[key]['entity'] + '/' + key
                else:
                    params['seeds'] = seeds[key]['collection'] + ':' + seeds[key]['entity'] + '/' + key
        if similarity_type is not None:
            params['similarity_type'] = similarity_type

        orig_collection = self.collection
        if collection_sim is not None: 
            self.collection = collection_sim
        method = '/tracks/similar_to'
        if not self.has_recommendations():
            return None
        doc = self._request(method, True, params) 
        self.collection = orig_collection
        
        list = []
        for node in doc.getElementsByTagName('track'):
            track_id = node.getAttribute('id') 
            if not track_id: continue

            relevance = float(_extract(node, 'relevance'))
            if threshold is not None and relevance < threshold:
                break
            artist_id = _extract(node, 'artist_service_id')
            if not artist_id: continue
            artist = Artist(artist_id, self.collection, self.ellaws)
            artist.set_name(_extract(node, 'artist'))
            if not artist.get_name(): continue

            popularity = _extract(node, 'artist_popularity')
            if not popularity:
                popularity = 0
            artist.set_popularity(popularity)

            location = _extract(node, 'artist_location')
            if not location:
                location = ''
            artist.set_location(location)

            recommendable = _extract(node, 'recommendable')
            if not recommendable:
                recommendable = True
            artist.set_recommend(recommendable)

            track = Track(track_id, artist, collection_sim, self.ellaws)
            track.title = _extract(node, 'track')
            track.audio = _extract(node, 'location')
            track.set_artist(artist)
            track.set_artist_name(artist.get_name())
            track.set_artist_id(artist.get_id())
            for link in self._metadata_links :
                track.set_link(link, _extract(node, link))
            if track.get_links() is None: track._links = []

            popularity = _extract(node, 'track_popularity')
            if not popularity:
                popularity = 0
            track.set_popularity(popularity)

            recommendable = _extract(node, 'recommendable')
            if not recommendable:
                recommendable = True
            track.set_recommend(recommendable)

            image = _extract(node, 'track_small_image')
            track.set_image(image)

            album_id = _extract(node, 'release_service_id')
            if album_id:
                album = Album(album_id, self.collection, self.ellaws)
                album.set_title(_extract(node, 'release'))
                album.set_artist(artist)
                album.set_image(_extract(node, 'release_small_image'))
                album.set_label(_extract(node, 'release_label'))
                track.set_album(album)
                track.set_album_title(album.get_title())
                track.set_album_id(album.get_id())
            else :
                track.set_album_title('')
                track.set_album_id('')

            list.append(track)
        self._similar_tracks = list
        return self._similar_tracks

    def get_links(self):
        """ Returns the metadata of the track """
        if not self._links :
            self._links = []
            try :
                if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
                for link in self._metadata_links :
                    self._links.append((link, _extract(self._xml, link)))
            except:
                return self._links
        return self._links

    def set_link(self, service, link) :
        """ Sets an external link for the track """
        if not self._links :
            self._links = []
        self._links.append((service, link))

    def get_popularity(self):
        """ Returns track popularity """
        if self._popularity is None :
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            popularity = _extract(self._xml, 'track_popularity')
            if popularity:
                self._popularity = round(float(popularity, 2))
            else:
                self._popularity = 0
        return self._popularity

    def set_popularity(self, popularity):
        """ Sets track popularity """
        self._popularity = float(popularity)

    def get_attribute(self, attr):
        """ Returns track attr value """
        if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': attr})
        return _extract_all(self._xml, attr)


class Tag(_BaseObject):
    """ A Bmat album """
    def __init__(self, id, collection='tags', ellaws=HOST_NAME):
        _BaseObject.__init__(self, collection, ellaws)
        
        self.id = id
        self.name = None
        self._method = '/tags/' + self.id + '.xml'

        self._tags = None
        self._similar_tracks = None
        self._similar_artists = None

        self._metadata = '_all'
        self._xml = None
    
    def __repr__(self):
       return self.get_name().encode('utf8')

    def __eq__(self, other):
        return self.get_id() == other.get_id()

    def __ne__(self, other):
        return self.get_id() != other.get_id()


    def get_id(self):
        """ Returns the bmat id """
        return self.id

    def get_name(self):
        """ Returns the tag name """
        if self.name is None:
            if not self._xml : self._xml = self._request(self._method, True, {'fetch_metadata': self._metadata})
            self.name = _extract(self._xml, 'name')
        return self.name

    def set_name(self, name):
        self.name = name

    def get_similar(self):
        """ Returns similar tags """
        if self._tags is None:
            self._tags = []
            limit = 100
            method = '/tags/%s/similar/collections/tags/tags' % self.id
            xml = self._request(method, True, {'fetch_metadata': 'tag_type', 'limit': str(limit)})
            for tag in xml.getElementsByTagName('tag') :
                tag_type = _extract(tag, 'tag_type')
                relevance = float(_extract(tag, 'relevance') or 0.0)
                if not tag_type == 'style' : continue
                self._tags.append( (relevance, tag.getAttribute('id')) )
        if self._tags : self._tags.sort(reverse=True)
        return self._tags

    def get_artists(self, limit=20, collection_ref='bmat'):
        list = []

        artist_metadata = 'artist,name,artist_popularity,artist_location,recommendable,artist_decades1,artist_decades2,artist_latlng,musicbrainz_artist_id,'
        artist_metadata_links = ['official_homepage_artist_url','wikipedia_artist_url','lastfm_artist_url','myspace_artist_url','spotify_artist_url','itms_artist_url','discogs_artist_url']
        artist_metadata += ','.join(artist_metadata_links)

        params = {}
        params['limit'] = str(limit)
        params['fetch_metadata'] = artist_metadata

        method = '/tags/%s/similar/collections/%s/artists' % (self.id, collection_ref)
        original_collection = self.collection
        doc = self._request(method, True, params) 
        self.collection = original_collection
        for node in doc.getElementsByTagName('artist'):
            artist_id = node.getAttribute('id') 
            relevance = _extract(node, 'relevance')
            if not relevance: continue
            relevance = float(relevance)

            if not artist_id: continue
            if self.collection:
                collection = self.collection
            else:
                collection = re.compile('/collections/([^/]+)/.+').match(node.getAttribute('href')).group(1)
                collection = collection.decode('utf8')

            artist = Artist(artist_id, collection_ref, self.ellaws)
            artist.set_name(_extract(node, 'name'))
            if not artist.get_name(): continue
            artist.set_mbid(_extract(node, 'musicbrainz_artist_id'))
            
            popularity = _extract(node, 'artist_popularity')
            if not popularity:
                popularity = 0
            artist.set_popularity(popularity)

            location = _extract(node, 'artist_location')
            if not location:
                location = ''
            artist.set_location(location)

            latlng = _extract(node, 'artist_latlng')
            if latlng:
                lat, lng = latlng.split(',')
                artist.set_lat(lat)
                artist.set_lng(lng)
            else:
                artist.set_lat(None)
                artist.set_lng(None)

            recommendable = _extract(node, 'recommendable')
            if not recommendable:
                recommendable = True
            artist.set_recommend(recommendable)

            list.append(artist)
        return list

    def get_tracks(self, limit=20, filter=None, collection_ref='bmat', seeds=None, random=True):
        """ Returns the similar tracks given a tag """
        params = {}
        params['limit'] = str(limit)

        track_metadata = 'track,artist_service_id,artist,release_service_id,release,location,year,genre,track_popularity,track_small_image,recommendable,musicbrainz_track_id,spotify_track_uri,'
        track_metadata_links = 'spotify_track_url,grooveshark_track_url,amazon_track_url,itms_track_url,hypem_track_url,musicbrainz_track_url'
        track_metadata += track_metadata_links
        params['fetch_metadata'] = track_metadata
        
        if filter:
            params['filter'] = ' AND '.join(filter)

	#Add tag id as seed
        params['seeds'] = self.collection + ':tag/' + self.id
        #Add more seeds
        if seeds :
            for key in seeds.keys():
                if params.has_key('seeds'):
                    params['seeds'] = params['seeds'] + ',' + seeds[key]['collection'] + ':' + seeds[key]['entity'] + '/' + key
                else:
                    params['seeds'] = seeds[key]['collection'] + ':' + seeds[key]['entity'] + '/' + key

        if random : 
            params['similarity_type'] = 'playlist'

        method = '/tracks/similar_to'
        original_collection = self.collection
        self.collection = 'bmat'
        doc = self._request(method, True, params) 
        self.collection = original_collection
        
        list = []
        for node in doc.getElementsByTagName('track'):
            track_id = node.getAttribute('id') 
            if not track_id: continue

            artist_id = _extract(node, 'artist_service_id')
            if not artist_id: continue
            artist = Artist(artist_id, collection_ref, self.ellaws)
            artist.set_name(_extract(node, 'artist'))
            if not artist.get_name(): continue

            popularity = _extract(node, 'artist_popularity')
            if not popularity:
                popularity = 0
            artist.set_popularity(popularity)

            location = _extract(node, 'artist_location')
            if not location:
                location = ''
            artist.set_location(location)

            recommendable = _extract(node, 'recommendable')
            if not recommendable:
                recommendable = True
            artist.set_recommend(recommendable)

            track = Track(track_id, artist, collection_ref, self.ellaws)
            track.title = _extract(node, 'track')
            track.audio = _extract(node, 'location')
            track.set_artist(artist)
            track.set_artist_name(artist.get_name())
            track.set_artist_id(artist.get_id())
            track.set_mbid(_extract(node, 'musicbrainz_track_id'))

            for link in track_metadata_links.split(',') :
                track.set_link(link, _extract(node, link))
            if track.get_links() is None: track._links = []

            popularity = _extract(node, 'track_popularity')
            if not popularity:
                popularity = 0
            track.set_popularity(popularity)

            recommendable = _extract(node, 'recommendable')
            if not recommendable:
                recommendable = True
            track.set_recommend(recommendable)

            image = _extract(node, 'track_small_image')
            track.set_image(image)

            album_id = _extract(node, 'release_service_id')
            if album_id:
                album = Album(album_id, collection_ref, self.ellaws)
                album.set_title(_extract(node, 'release'))
                album.set_artist(artist)
                album.set_image(_extract(node, 'release_small_image'))
                album.set_label(_extract(node, 'release_label'))
                track.set_album(album)
                track.set_album_title(album.get_title())
                track.set_album_id(album.get_id())
            else :
                track.set_album_title('')
                track.set_album_id('')

            list.append(track)
        self._similar_tracks = list
        return self._similar_tracks

class _Search(_BaseObject):
    """ An abstract class for search """

    def __init__(self, method, search_terms, collection, ellaws=HOST_NAME):
        _BaseObject.__init__(self, collection, ellaws)

        self.search_terms = search_terms
        self.method = method

        self._results_per_page = 10
        if self.search_terms.has_key('limit'):
            self._results_per_page = int(self.search_terms['limit'])
        else:
            self.search_terms['limit'] = self._results_per_page
        
        self._last_page_index = -1
        self._hits = None

    def get_total_result_count(self):
        if self._hits is not None: return self._hits

        params = self._get_params()
        if self.method.find('resolve') == -1 :
            params['offset'] = '0'
        params['limit'] = '1'
        params['fetch_metadata'] = '_none'
        xml = self._request(self.method, True, params)
        if self.collection != None:
            hits = int(_extract(xml, 'total_hits'))
        else:
            hits = 0
            hits_xml = xml.getElementsByTagName('total_hits')[0]
            for node in hits_xml.childNodes:
                if node.nodeType == node.ELEMENT_NODE:
                    hits += int(node.firstChild.data.strip())
        self._hits = hits
        return self._hits

    def _get_params(self):
        params = {}

        for key in self.search_terms.keys():
            params[key] = self.search_terms[key]

        return params

    def _retrieve_page(self, page_index):
        """ Returns the node of matches to be processed """

        params = self._get_params()
        if self.method.find('resolve') == -1 :
            offset = 0
            if page_index != 0: 
                offset = self._results_per_page * page_index
            params["offset"] = str(offset)
        doc = self._request(self.method, True, params)
        return doc.getElementsByTagName("results")[0]

    def _retrieve_next_page(self):
        self._last_page_index += 1
        return self._retrieve_page(self._last_page_index)

class TrackSearch(_Search):
    """ Search for tracks """

    def __init__(self, query, collection, ellaws=HOST_NAME, fuzzy=False, method='search', threshold=None, filter=None):
        self._metadata = 'track,artist_service_id,artist,release_service_id,release,location,year,genre,track_popularity,track_small_image,recommendable,musicbrainz_track_id,spotify_track_uri,'
        self._metadata_links = ['spotify_track_url', 'grooveshark_track_url', 'amazon_track_url','musicbrainz_track_url','hypem_track_url']
        self._metadata += ','.join(self._metadata_links)
        self._method = method
        self._fuzzy = fuzzy
        self._threshold = threshold

        if method == 'resolve' :
            artist = query['artist']
            track = query['track']
            _Search.__init__(self, '/tracks/' + self._method + '.xml', {'artist': artist, 'track': track, 'limit': '100', 'fetch_metadata': self._metadata }, collection, ellaws)
        elif not self._fuzzy : #If not fuzzy => it's a search
            if filter is None:
                _Search.__init__(self, '/tracks/' + self._method + '.xml', {'q': 'trackartist:' + query, 'limit': '10', 'fetch_metadata': self._metadata }, collection, ellaws)
            else:
                if not query:
                    query = ''
                query += ' AND '.join(filter)
                _Search.__init__(self, '/tracks/' + self._method + '.xml', {'q': query, 'limit': '10', 'fetch_metadata': self._metadata }, collection, ellaws)
        else :
            _Search.__init__(self, '/tracks/match.xml', {'q': query, 'limit': '30', 'fuzzy' : 'true','fetch_metadata': self._metadata }, collection, ellaws)
            self._fuzzy = True

    def get_next_page(self):
        master_node = self._retrieve_next_page()
        return self._get_results(master_node)

    def get_page(self, page=0):
        if page < 0: page = 0
        if page > 0: page=page-1
        
        master_node = self._retrieve_page(page)
        return self._get_results(master_node)

    def _get_results(self, master_node):
        list = []
        for node in master_node.getElementsByTagName('track'):
            track_id = node.getAttribute('id') 
            if not track_id: continue
            if self.collection:
                collection = self.collection
            else:
                collection = re.compile('/collections/([^/]+)/.+').match(node.getAttribute('href')).group(1)
                collection = collection.decode('utf8')

            relevance = float(_extract(node, 'relevance'))
            if self._fuzzy and relevance < 0.4 : continue
            if self._method == 'resolve' and relevance < self._threshold: continue #0.75
            if self._method == 'match' and relevance < self._threshold : continue #0.60

            artist_id = _extract(node, 'artist_service_id')
            if not artist_id: continue
            artist = Artist(artist_id, collection, self.ellaws)
            artist.name = _extract(node, 'artist')
            if not artist.get_name(): continue

            popularity = _extract(node, 'artist_popularity')
            if not popularity:
                popularity = 0
            artist.set_popularity(popularity)

            location = _extract(node, 'artist_location')
            if not location:
                location = ''
            artist.set_location(location)

            recommendable = _extract(node, 'recommendable')
            if not recommendable:
                recommendable = True
            artist.set_recommend(recommendable)

            track = Track(track_id, artist, collection, self.ellaws)
            track.title = _extract(node, 'track')
            track.audio = _extract(node, 'location')
            track.set_artist(artist)
            track.set_artist_name(artist.get_name())
            track.set_artist_id(artist.get_id())
            track.set_mbid(_extract(node, 'musicbrainz_track_id'))

            popularity = _extract(node, 'track_popularity')
            if not popularity:
                popularity = 0
            track.set_popularity(popularity)

            recommendable = _extract(node, 'recommendable')
            if not recommendable:
                recommendable = True
            track.set_recommend(recommendable)

            for link in self._metadata_links :
                track.set_link(link, _extract(node, link))
            if track.get_links() is None: track._links = []
            image = _extract(node, 'track_small_image')
            track.set_image(image)
            
            album_id = _extract(node, 'release_service_id')
            if album_id:
                album = Album(album_id, collection, self.ellaws)
                album.set_title(_extract(node, 'release'))
                album.set_artist(artist)
                album.set_image(_extract(node, 'release_small_image'))
                album.set_label(_extract(node, 'release_label'))

                track.set_album(album)
                track.set_album_title(album.get_title())
                track.set_album_id(album.get_id())
            else :
                track.set_album_title('')
                track.set_album_id('')
            list.append(track)
        return list

class TagSearch(_Search):
    """ Search for tracks """

    def __init__(self, query, collection='tags', ellaws=HOST_NAME, fuzzy=False, method='search'):
        self._metadata = '_all'
        self._method = method

        self._fuzzy = fuzzy
        if not fuzzy :
            _Search.__init__(self, '/tags/' + self._method + '.xml', {'q': query, 'limit': '10', 'fetch_metadata': self._metadata }, collection, ellaws)
        else :
            _Search.__init__(self, '/tags/match.xml', {'q': query, 'limit': '30', 'fuzzy' : 'True', 'fetch_metadata': self._metadata }, collection, ellaws)
            self._fuzzy = True

    def get_next_page(self):
        master_node = self._retrieve_next_page()
        return self._get_results(master_node)

    def get_page(self, page=0):
        if page < 0: page = 0
        if page > 0: page=page-1
        
        master_node = self._retrieve_page(page)
        return self._get_results(master_node)

    def _get_results(self, master_node):
        list = []
        for node in master_node.getElementsByTagName('tag'):
            tag_id = node.getAttribute('id') 
            if not tag_id: continue
            if self.collection:
                collection = self.collection
            else:
                collection = re.compile('/collections/([^/]+)/.+').match(node.getAttribute('href')).group(1)
                collection = collection.decode('utf8')

            if self._fuzzy and float(_extract(node, 'relevance')) < 0.4 : continue
            if self._method == 'match' and float(_extract(node, 'relevance')) < 0.7 : continue

            tag = Tag(tag_id, collection, self.ellaws)
            tag.set_name(_extract(node, 'name'))
            list.append(tag)
        return list

class ArtistSearch(_Search):
    """ Fuzzy Search for artists """

    def __init__(self, query, collection, ellaws=HOST_NAME, fuzzy=False, method='search', threshold=None):
        self._metadata = 'name,relevance,recommendable,artist_decades1,artist_decades2,artist_location,artist_latlng,artist_popularity,musicbrainz_artist_id,'
        self._metadata_links = ['official_homepage_artist_url','wikipedia_artist_url','lastfm_artist_url','myspace_artist_url','spotify_artist_url','discogs_artist_url']
        self._metadata += ','.join(self._metadata_links)
        self._method = method
        self._fuzzy = fuzzy
        self._threshold = threshold

        if method == 'resolve' :
            _Search.__init__(self, '/artists/' + self._method + '.xml', {'artist': query, 'limit': '100', 'fetch_metadata': self._metadata }, collection, ellaws)
        elif not self._fuzzy : #If not fuzzy => it's a search
            _Search.__init__(self, '/artists/' + self._method + '.xml', {'q': query, 'limit': '100', 'fetch_metadata': self._metadata }, collection, ellaws)
        else :
            _Search.__init__(self, '/artists/match.xml', {'q': query, 'limit': '30', 'fuzzy' : 'true','fetch_metadata': self._metadata }, collection, ellaws)
            self._fuzzy = True

    def get_next_page(self):
        master_node = self._retrieve_next_page()
        return self._get_results(master_node)

    def get_page(self, page=0):
        if page < 0: page = 0
        if page > 0: page=page-1
        
        master_node = self._retrieve_page(page)
        return self._get_results(master_node)

    def _get_results(self, master_node):
        list = []
        for node in master_node.getElementsByTagName('artist'):
            artist_id = node.getAttribute('id') 
            relevance = _extract(node, 'relevance')
            if not relevance: continue
            relevance = float(relevance)
            if self._fuzzy and relevance < 0.4 : continue
            if self._method == 'resolve' and relevance < self._threshold: continue #0.75
            if self._method == 'match' and relevance < self._threshold : continue #0.60

            if not artist_id: continue
            if self.collection:
                collection = self.collection
            else:
                collection = re.compile('/collections/([^/]+)/.+').match(node.getAttribute('href')).group(1)
                collection = collection.decode('utf8')

            artist = Artist(artist_id, collection, self.ellaws)
            artist.set_name(_extract(node, 'name'))
            if not artist.get_name(): continue
            artist.set_mbid(_extract(node, 'musicbrainz_artist_id'))
            
            popularity = _extract(node, 'artist_popularity')
            if not popularity:
                popularity = 0
            artist.set_popularity(popularity)

            location = _extract(node, 'artist_location')
            if not location:
                location = ''
            artist.set_location(location)

            latlng = _extract(node, 'artist_latlng')
            if latlng:
                lat, lng = latlng.split(',')
                artist.set_lat(lat)
                artist.set_lng(lng)
            else:
                artist.set_lat(None)
                artist.set_lng(None)

            recommendable = _extract(node, 'recommendable')
            if not recommendable:
                recommendable = True
            artist.set_recommend(recommendable)

            list.append(artist)
        return list[0:5]

def search_tracks(query, collection='bmat', ellaws=HOST_NAME, fuzzy=False, filter=None):
    """Searches of a track by query. Returns a TrackSearch object.
    Use get_next_page() to retrieve sequences of results."""
    return TrackSearch(query, collection, ellaws, fuzzy, 'search', None, filter)

def search_artists(query, collection='bmat', ellaws=HOST_NAME, fuzzy=False):
    """Searches of an artist by query. Returns an ArtistSearch object.
    Use get_next_page() to retrieve sequences of results."""
    return ArtistSearch(query, collection, ellaws, fuzzy)

def search_tags(query, collection='tags', ellaws=HOST_NAME, fuzzy=False):
    """Searches of a track by query. Returns a TagSearch object.
    Use get_next_page() to retrieve sequences of results."""
    return TagSearch(query, collection, ellaws, fuzzy)

#XML stuff here...
def _extract(node, name, index = 0):
    """Extracts a value from the xml string"""
    try:
        nodes = node.getElementsByTagName(name)
        
        if len(nodes):
            if nodes[index].firstChild:
                return nodes[index].firstChild.data.strip()
            else:
                return None
    except:
        return None

def _extract_all(node, name, limit_count = None):
    """Extracts all the values from the xml string. returning a list."""
    
    list = []
    
    for i in range(0, len(node.getElementsByTagName(name))):
        if len(list) == limit_count:
            break
        list.append(_extract(node, name, i))
    return list

def enable_caching(cache_dir = None):
    global __cache_dir
    global __cache_enabled

    if cache_dir == None:
        import tempfile
        __cache_dir = tempfile.mkdtemp()
    else:
        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir)
        __cache_dir = cache_dir
    __cache_enabled = True

def disable_caching():
    global __cache_enabled
    __cache_enabled = False

def is_caching_enabled():
    """Returns True if caching is enabled."""
    global __cache_enabled
    return __cache_enabled

def _get_cache_dir():
    """Returns the directory in which cache files are saved."""
    global __cache_dir
    global __cache_enabled
    return __cache_dir

def get_md5(text):
    """Returns the md5 hash of a string."""
    hash = md5()
    hash.update(text.encode('utf8'))
    return hash.hexdigest()

