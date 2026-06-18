import math, statistics as st, json, unicodedata, os, datetime
norm=lambda s:''.join(c for c in unicodedata.normalize('NFKD',s) if not unicodedata.combining(c)).lower().replace('.','').strip()
def ln(s):
    t=[w for w in norm(s).split() if w not in('jr','sr','ii','iii')]; return t[-1]
clamp=lambda x,a,b:max(a,min(b,x))
fF=lambda f:1.0 if f is None else clamp(1+0.006*(f-50),0.85,1.15)
mM=lambda h:1.0 if h is None else clamp(1+0.20*((h-1.25)/0.6),0.82,1.18)
pM=lambda w:1.0 if w is None else 1+(0.25 if w<1 else 0.30)*(w-1)
la_window=lambda la:math.exp(-((la-25.0)/14.0)**2)

# ---- ISO sheet (101) ----
ISO_RAW={'Byron Buxton': 0.326, 'Ben Rice': 0.32, 'Kyle Schwarber': 0.32, 'Yordan Alvarez': 0.318, 'Hunter Goodman': 0.285, 'Aaron Judge': 0.285, 'Colson Montgomery': 0.277, 'Matt Olson': 0.276, 'Brandon Lowe': 0.271, 'James Wood': 0.27, 'Dillon Dingler': 0.267, 'Corbin Carroll': 0.264, 'Nick Kurtz': 0.261, 'Juan Soto': 0.258, 'Willson Contreras': 0.257, 'Max Muncy': 0.256, 'Jordan Walker': 0.249, 'Christian Walker': 0.249, 'Shohei Ohtani': 0.249, 'Shea Langeliers': 0.247, 'Ian Happ': 0.246, 'Drake Baldwin': 0.242, 'Kody Clemens': 0.242, 'Miguel Vargas': 0.24, 'Mike Trout': 0.238, 'Jake Bauers': 0.237, 'Bryce Harper': 0.231, 'Pete Crow-Armstrong': 0.23, 'Elly De La Cruz': 0.228, 'Tyler Soderstrom': 0.227, 'Casey Schmitt': 0.226, 'CJ Abrams': 0.221, 'Zach Neto': 0.221, 'Andy Pages': 0.22, 'Gavin Sheets': 0.216, 'Pete Alonso': 0.216, 'Junior Caminero': 0.213, 'Michael Harris': 0.208, 'Oneil Cruz': 0.208, 'Cody Bellinger': 0.207, 'Brice Turang': 0.206, 'Willy Adames': 0.205, 'Sal Stewart': 0.204, 'Spencer Torkelson': 0.204, 'Angel Martinez': 0.204, 'Alec Burleson': 0.203, 'Freddie Freeman': 0.202, 'Liam Hicks': 0.198, 'Gunnar Henderson': 0.195, 'Luis Garcia': 0.195, 'Rafael Devers': 0.191, 'Bryan Reynolds': 0.19, 'TJ Rumfield': 0.188, 'Yandy Diaz': 0.187, 'Jake Burger': 0.186, "Ryan O'Hearn": 0.186, 'Andrew Benintendi': 0.185, 'Spencer Steer': 0.184, 'Ketel Marte': 0.184, 'Jarren Duran': 0.183, 'Jorge Soler': 0.182, 'Carter Jensen': 0.181, 'Manny Machado': 0.181, 'Isaac Paredes': 0.18, 'Julio Rodriguez': 0.179, 'Jose Ramirez': 0.179, 'Seiya Suzuki': 0.179, 'Brandon Marsh': 0.177, 'Jazz Chisholm': 0.177, 'Brooks Lee': 0.177, 'J.P. Crawford': 0.176, 'Spencer Horwitz': 0.175, 'Trent Grisham': 0.174, 'Garrett Mitchell': 0.171, 'Jonathan Aranda': 0.169, 'Ronald Acuna': 0.169, 'Jac Caglianone': 0.164, 'Bobby Witt': 0.162, 'Ceddanne Rafaela': 0.161, 'Jacob Young': 0.159, 'Ivan Herrera': 0.159, 'Bryson Stott': 0.158, 'Daylen Lile': 0.158, 'Randy Arozarena': 0.157, 'Matt McLain': 0.156, 'Michael Busch': 0.154, 'Nolan Arenado': 0.154, 'Wilyer Abreu': 0.154, 'Josh Jung': 0.153, 'Ozzie Albies': 0.153, 'Daulton Varsho': 0.152, 'Ernie Clement': 0.151, 'Brandon Nimmo': 0.151, 'Riley Greene': 0.149, 'Mauricio Dubon': 0.149, 'Matt Chapman': 0.148, 'Ildemaro Vargas': 0.148, 'Kevin McGonigle': 0.147, 'Chase DeLauter': 0.146, 'Kyle Tucker': 0.146}
ISO={norm(k):v for k,v in ISO_RAW.items()}
ISO_FLOOR=min(ISO.values())

# ---- consensus median American odds for the 33-bat betting pool only ----
ODDS_RAW={'Byron Buxton': 273, 'Kody Clemens': 345, 'Royce Lewis': 510, 'Josh Bell': 458, 'Luke Keaschall': 1000, 'Trevor Larnach': 583, 'Victor Caratini': 638, 'Tristan Gray': 625, 'Brooks Lee': 605, 'Joc Pederson': 395, 'Wyatt Langford': 548, 'Jake Burger': 485, 'Kyle Higashioka': 690, 'Brandon Nimmo': 400, 'Josh Jung': 650, 'Josh Smith': 900, 'Pete Alonso': 368, 'Taylor Ward': 558, 'Adley Rutschman': 523, 'Samuel Basallo': 425, 'Colton Cowser': 535, 'Gunnar Henderson': 405, 'Jackson Holliday': 690, 'Cal Raleigh': 278, 'Dominic Canzone': 438, 'Mitch Garver': 700, 'Luke Raley': 473, 'Rob Refsnyder': 650, 'Julio Rodriguez': 400, 'Cole Young': 820, 'Colt Emerson': 750, 'J.P. Crawford': 710, 'Juan Soto': 238, 'Jared Young': 460, 'Carson Benge': 485, 'MJ Melendez': 440, 'Francisco Alvarez': 473, 'Brett Baty': 533, 'Bo Bichette': 560, 'Marcus Semien': 533, 'Kyle Schwarber': 203, 'Bryson Stott': 880, 'J.T. Realmuto': 575, 'Alec Bohm': 560, 'Brandon Marsh': 640, 'Bryce Harper': 425, 'Colson Montgomery': 335, 'Miguel Vargas': 268, 'Sam Antonacci': 1000, 'Randal Grichuk': 290, 'Braden Montgomery': 510, 'Chase Meidroth': 800, 'Ben Rice': 240, 'Paul Goldschmidt': 323, 'Jazz Chisholm': 300, 'Cody Bellinger': 350, 'Ryan McMahon': 395, 'Jasson Dominguez': 445, 'J.C. Escarra': 820, 'Spencer Jones': 395, 'Rhys Hoskins': 483, 'Kyle Manzardo': 495, 'David Fry': 600, 'Steven Kwan': 1500, 'Travis Bazzana': 820, 'Stuart Fairchild': 900, 'Gary Sanchez': 483, 'Andrew Vaughn': 550, 'Brice Turang': 850, 'Jackson Chourio': 475, 'William Contreras': 575, 'Joey Ortiz': 1120, 'Garrett Mitchell': 880, 'Lars Nootbaar': 950, 'Nelson Velazquez': 410, 'Ivan Herrera': 560, 'JJ Wetherholt': 495, 'Alec Burleson': 523, 'Jordan Walker': 333, 'Nathan Church': 1000, 'Masyn Winn': 920, 'Bobby Witt': 400, 'Nick Loftin': 1000, 'Maikel Garcia': 850, 'Lane Thomas': 650, 'Jac Caglianone': 483, 'Michael Massey': 820, 'Salvador Perez': 495, 'Isaac Collins': 800, 'Kazuma Okamoto': 483, 'Vladimir Guerrero Jr.': 533, 'Jesus Sanchez': 545, 'George Springer': 483, 'Yohendrick Pinango': 640, 'Brandon Valenzuela': 820, 'Wilyer Abreu': 395, 'Willson Contreras': 423, 'Masataka Yoshida': 990, 'Mickey Gasper': 750, 'Jarren Duran': 545, 'Caleb Durbin': 920, 'Andruw Monasterio': 850, 'Marcelo Mayer': 920, 'Rafael Devers': 538, 'Bryce Eldridge': 588, 'Matt Chapman': 535, 'Willy Adames': 520, 'Casey Schmitt': 500, 'Matt Olson': 460, 'Drake Baldwin': 533, 'Austin Riley': 613, 'Mike Yastrzemski': 980, 'Michael Harris': 540, 'Ha-Seong Kim': 1300, 'Dominic Smith': 900, 'Ozzie Albies': 900, 'Mike Trout': 308, 'Jo Adell': 313, 'Zach Neto': 340, "Logan O'Hoppe": 483, 'Vaughn Grissom': 585, 'Jose Siri': 458, 'Nick Kurtz': 290, 'Shea Langeliers': 295, 'Tyler Soderstrom': 508, 'Carlos Cortes': 750, 'Lawrence Butler': 630, 'Zack Gelof': 508}
ODDS={norm(k):v for k,v in ODDS_RAW.items()}   # full-board consensus, freshest snapshot

# form arrows for the 33 (note flavor only; TOTAL ignores arrow)
FT_RAW={'Davis Schneider': 'up', 'Kazuma Okamoto': 'up', 'Vladimir Guerrero Jr.': 'down', 'Jesus Sanchez': 'down', 'George Springer': 'up', 'Yohendrick Pinango': 'down', 'Brandon Valenzuela': 'down', 'Myles Straw': 'down', 'Wilyer Abreu': 'down', 'Willson Contreras': 'down', 'Masataka Yoshida': 'up', 'Mickey Gasper': 'down', 'Jarren Duran': 'up', 'Caleb Durbin': 'up', 'Andruw Monasterio': 'down', 'Carlos Narvaez': 'down', 'Marcelo Mayer': 'up', 'Rhys Hoskins': 'down', 'Kyle Manzardo': 'up', 'Petey Halpin': 'up', 'David Fry': 'up', 'Daniel Schneemann': 'up', 'Steven Kwan': 'down', 'Travis Bazzana': 'down', 'Patrick Bailey': 'down', 'Stuart Fairchild': 'down', 'Jake Bauers': 'up', 'Gary Sanchez': 'up', 'Andrew Vaughn': 'down', 'Sal Frelick': 'down', 'Brice Turang': 'down', 'Jackson Chourio': 'up', 'William Contreras': 'up', 'Joey Ortiz': 'down', 'Garrett Mitchell': 'down', 'Byron Buxton': 'up', 'Kody Clemens': 'down', 'Royce Lewis': 'up', 'Josh Bell': 'down', 'Luke Keaschall': 'up', 'Trevor Larnach': 'up', 'Victor Caratini': 'down', 'Tristan Gray': 'down', 'Brooks Lee': 'down', 'Joc Pederson': 'up', 'Jake Burger': 'up', 'Kyle Higashioka': 'up', 'Brandon Nimmo': 'down', 'Josh Jung': 'up', 'Justin Foscue': 'up', 'Josh Smith': 'up', 'Pete Alonso': 'down', "Tyler O'Neill": 'up', 'Taylor Ward': 'up', 'Adley Rutschman': 'down', 'Samuel Basallo': 'down', 'Colton Cowser': 'up', 'Gunnar Henderson': 'up', 'Coby Mayo': 'down', 'Jackson Holliday': 'up', 'Cal Raleigh': 'up', 'Dominic Canzone': 'up', 'Mitch Garver': 'down', 'Luke Raley': 'up', 'Rob Refsnyder': 'up', 'Julio Rodriguez': 'down', 'Cole Young': 'down', 'Colt Emerson': 'up', 'J.P. Crawford': 'up', 'Jared Young': 'down', 'Carson Benge': 'up', 'MJ Melendez': 'up', 'Mark Vientos': 'down', 'Brett Baty': 'down', 'Bo Bichette': 'up', 'Marcus Semien': 'down', 'Kyle Schwarber': 'up', 'Bryson Stott': 'down', 'J.T. Realmuto': 'down', 'Alec Bohm': 'up', 'Brandon Marsh': 'down', 'Bryce Harper': 'down', 'Rafael Marchan': 'down', 'Colson Montgomery': 'down', 'Miguel Vargas': 'up', 'Sam Antonacci': 'up', 'Randal Grichuk': 'down', 'Andrew Benintendi': 'up', 'Chase Meidroth': 'down', 'Ben Rice': 'down', 'Paul Goldschmidt': 'up', 'Jazz Chisholm': 'down', 'Cody Bellinger': 'down', 'Ryan McMahon': 'up', 'Anthony Volpe': 'down', 'J.C. Escarra': 'down', 'Spencer Jones': 'up', 'Bryce Eldridge': 'down', 'Matt Chapman': 'down', 'Willy Adames': 'up', 'Victor Bericoto': 'down', 'Casey Schmitt': 'down', 'Eric Haase': 'down', 'Matt Olson': 'down', 'Drake Baldwin': 'up', 'Austin Riley': 'down', 'Mike Yastrzemski': 'down', 'Michael Harris': 'down', 'Ha-Seong Kim': 'down', 'Dominic Smith': 'up', 'Ozzie Albies': 'down', 'Lars Nootbaar': 'up', 'Nelson Velazquez': 'up', 'Ivan Herrera': 'up', 'JJ Wetherholt': 'down', 'Alec Burleson': 'up', 'Jordan Walker': 'down', 'Jimmy Crooks': 'up', 'Nathan Church': 'down', 'Masyn Winn': 'up', 'Bobby Witt': 'up', 'Nick Loftin': 'up', 'Maikel Garcia': 'up', 'Lane Thomas': 'down', 'Jac Caglianone': 'down', 'Michael Massey': 'up', 'Salvador Perez': 'down', 'Isaac Collins': 'up', 'Mike Trout': 'up', 'Jo Adell': 'up', 'Zach Neto': 'down', "Logan O'Hoppe": 'up', 'Donovan Walton': 'down', 'Nolan Schanuel': 'down', 'Vaughn Grissom': 'up', 'Jose Siri': 'up', 'Nick Kurtz': 'down', 'Max Muncy (ATH)': 'up', 'Tyler Soderstrom': 'down', 'Colby Thomas': 'down', 'Carlos Cortes': 'up', 'Lawrence Butler': 'up', 'Jonah Heim': 'up'}
FT={norm(k):v for k,v in FT_RAW.items()}

FULL={'TOR':'Blue Jays','BOS':'Red Sox','CLE':'Guardians','MIL':'Brewers','MIN':'Twins','TEX':'Rangers','BAL':'Orioles','SEA':'Mariners','NYM':'Mets','PHI':'Phillies','CWS':'White Sox','NYY':'Yankees','SF':'Giants','ATL':'Braves','STL':'Cardinals','KC':'Royals','LAA':'Angels','ATH':'Athletics','COL':'Rockies','CHC':'Cubs','TB':'Rays','LAD':'Dodgers','MIA':'Marlins','PIT':'Pirates','DET':'Tigers','HOU':'Astros','CIN':'Reds','AZ':'Diamondbacks','ARI':'Diamondbacks','WSH':'Nationals','SD':'Padres'}
# game: gmatch -> gn,gtime,wf,opp_for_away(SP that away hitters face = home SP),opp_for_home(=away SP); hr9 by opp; hands
# ---- auto-pulled inputs from fetch_mlb.py: weather->wf and pitcher HR/9, per matchup ----
# slate_auto_<DATE>.json is produced/refreshed by the GitHub Action; the scorer reads
# it at score time so wf and HR/9 reflect the latest pull (and update through the day).
def load_slate(date):
    try:
        s=json.load(open(f'slate_auto_{date}.json'))
    except Exception as e:
        print(f"  (no slate_auto_{date}.json — wf/HR9 fall back to hardcoded: {e})")
        return {}
    out={}
    for g in s.get('games',[]):
        sp={}; lu={}; conf=set()
        for side in ('away','home'):
            sd=g.get(side,{}) or {}
            spd=sd.get('sp',{}) or {}
            if spd.get('name'): sp[norm(spd['name'])]=spd.get('hr9')
            ab=sd.get('abbrev')
            nset={norm(b.get('name','')) for b in (sd.get('lineup') or []) if b.get('name')}
            if ab and nset:
                lu[ab]=nset                              # this team's card is POSTED
                if sd.get('confirmed'): conf.add(ab)     # ...and OFFICIAL (not just a projected/expected lineup)
        out[g.get('matchup','')]={'wf':g.get('wf'),'weather':g.get('weather',{}),'sp':sp,'lu':lu,'conf':conf}
    return out
DATE=os.environ.get('SLATE_DATE') or (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=4)).strftime('%Y-%m-%d')
SLATE=load_slate(DATE)

GAMES=[
 ('TOR@BOS',1,'1:35 PM',1.08,'TOR','BOS',('Trey Yesavage','RHP',None),('Sonny Gray','RHP',None)),
 ('CLE@MIL',2,'2:10 PM',1.00,'CLE','MIL',('Parker Messick','LHP',None),('Shane Drohan','LHP',None)),
 ('MIN@TEX',3,'2:35 PM',1.00,'MIN','TEX',('Joe Ryan','RHP',None),('Jack Leiter','RHP',None)),
 ('BAL@SEA',4,'4:10 PM',1.00,'BAL','SEA',('Shane Baz','RHP',None),('Bryan Woo','RHP',None)),
 ('NYM@PHI',5,'6:40 PM',1.08,'NYM','PHI',('Sean Manaea','LHP',None),('Aaron Nola','RHP',None)),
 ('CWS@NYY',6,'7:05 PM',1.08,'CWS','NYY',('Sean Burke','RHP',None),('Ryan Weathers','LHP',None)),
 ('SF@ATL',7,'7:15 PM',1.043,'SF','ATL',('Landen Roupp','RHP',None),('Martin Perez','LHP',None)),
 ('STL@KC',8,'7:40 PM',1.012,'STL','KC',('Matthew Liberatore','LHP',None),('Noah Cameron','LHP',None)),
 ('LAA@ATH',9,'9:40 PM',1.018,'LAA','ATH',('Jose Soriano','RHP',None),('Gage Jump','LHP',None)),
]
# hitter rows per team: name, aT, zone, form, pb, hh, la
ROWS={
'TOR':[('Davis Schneider', 80.9, 0.037, 46, 7.7, 52.0, 21.3),('Kazuma Okamoto', 75.2, 0.038, 44, 7.6, 58.1, 19.9),('Vladimir Guerrero Jr.', 73.0, 0.039, 51, 6.9, 57.0, 12.8),('Jesus Sanchez', 72.5, 0.088, 26, 6.6, 54.6, 15.7),('George Springer', 70.5, 0.065, 36, 6.8, 46.9, 15.6),('Yohendrick Pinango', 67.2, 0.051, 48, 6.5, 53.8, 16.9),('Brandon Valenzuela', 66.4, 0.058, 50, 7.0, 45.5, 20.5),('Alejandro Kirk', 63.8, 0.045, 49, 3.4, 50.6, 18.6),('Myles Straw', 55.0, 0.039, 40, 1.1, 26.2, 19.8)],
'BOS':[('Wilyer Abreu', 62.9, 0.092, 57, 8.3, 52.7, 25.3),('Willson Contreras', 58.3, 0.09, 41, 7.1, 55.0, 14.7),('Masataka Yoshida', 47.0, 0.054, 63, 3.5, 46.4, 11.1),('Mickey Gasper', 47.0, 0.07, 55, 0.5, 49.7, 14.6),('Jarren Duran', 46.7, 0.069, 45, 4.8, 47.2, 17.1),('Caleb Durbin', 45.6, 0.08, 71, 2.8, 31.8, 15.4),('Andruw Monasterio', 45.9, 0.044, 43, 3.4, 36.9, 21.9),('Carlos Narvaez', 44.6, 0.075, 41, 4.3, 49.0, 19.7),('Marcelo Mayer', 44.0, 0.082, 57, 3.9, 50.2, 11.2)],
'CLE':[('Rhys Hoskins', 74.6, 0.042, 51, 8.4, 54.2, 22.0),('Kyle Manzardo', 64.5, 0.055, 51, 8.2, 50.8, 22.8),('Petey Halpin', 55.8, 0.031, 56, 0.0, 26.8, 21.0),('David Fry', 55.3, 0.057, 54, 5.7, 51.1, 21.2),('Daniel Schneemann', 53.7, 0.069, 53, 5.1, 43.6, 17.0),('Steven Kwan', 50.1, 0.068, 60, 1.3, 22.1, 19.7),('Travis Bazzana', 49.9, 0.053, 39, 4.0, 42.7, 16.1),('Patrick Bailey', 49.4, 0.111, 45, 3.9, 43.9, 16.4),('Stuart Fairchild', 46.6, 0.032, 49, 5.9, 37.8, 17.3)],
'MIL':[('Jake Bauers', 71.5, 0.057, 62, 8.5, 55.2, 19.1),('Gary Sanchez', 70.3, 0.119, 44, 8.9, 52.7, 17.4),('Andrew Vaughn', 61.8, 0.091, 49, 5.2, 51.3, 17.8),('Sal Frelick', 55.4, 0.056, 55, 1.7, 29.6, 16.9),('Brice Turang', 54.7, 0.036, 33, 2.7, 40.6, 18.8),('Jackson Chourio', 54.2, 0.073, 62, 5.1, 48.8, 16.0),('William Contreras', 52.5, 0.086, 51, 4.8, 52.0, 11.5),('Joey Ortiz', 50.6, 0.069, 58, 2.3, 40.5, 16.7),('Garrett Mitchell', 50.6, 0.056, 45, 6.4, 45.0, 13.4)],
'MIN':[('Byron Buxton', 72.3, 0.064, 62, 13.5, 61.6, 19.1),('Kody Clemens', 58.7, 0.056, 62, 6.2, 52.7, 19.9),('Royce Lewis', 57.9, 0.07, 58, 7.6, 48.0, 20.6),('Josh Bell', 55.0, 0.075, 34, 5.7, 49.6, 16.3),('Luke Keaschall', 53.5, 0.082, 44, 3.2, 37.6, 16.2),('Trevor Larnach', 52.0, 0.065, 62, 6.2, 49.0, 13.8),('Victor Caratini', 51.5, 0.08, 48, 5.0, 46.0, 13.9),('Tristan Gray', 51.2, 0.04, 30, 7.8, 52.4, 20.5),('Brooks Lee', 48.8, 0.094, 66, 4.4, 41.4, 15.5)],
'TEX':[('Joc Pederson', 85.4, 0.091, 66, 8.1, 59.0, 20.8),('Wyatt Langford', 84.2, 0.061, 50, 8.1, 54.2, 20.7),('Jake Burger', 81.3, 0.074, 43, 7.5, 55.7, 16.3),('Kyle Higashioka', 80.9, 0.057, 48, 6.9, 51.3, 18.9),('Brandon Nimmo', 71.9, 0.088, 39, 5.8, 54.9, 17.5),('Josh Jung', 66.5, 0.071, 40, 4.0, 49.5, 15.8),('Justin Foscue', 64.7, 0.045, 51, 4.9, 44.3, 24.4),('Josh Smith', 62.2, 0.081, 54, 3.1, 41.0, 17.4),('Cody Freeman', 61.5, 0.082, None, 3.7, 31.5, 19.8)],
'BAL':[('Pete Alonso', 81.1, 0.125, 42, 8.6, 58.3, 20.0),("Tyler O'Neill", 72.8, 0.098, 56, 9.2, 51.7, 20.8),('Taylor Ward', 70.3, 0.081, 66, 6.3, 45.9, 20.0),('Adley Rutschman', 65.9, 0.059, 29, 5.1, 46.2, 19.0),('Samuel Basallo', 66.2, 0.075, 32, 7.3, 55.4, 16.5),('Colton Cowser', 65.1, 0.044, 74, 8.1, 46.2, 15.7),('Gunnar Henderson', 62.0, 0.072, 56, 6.6, 57.2, 15.4),('Coby Mayo', 62.2, 0.097, 42, 5.9, 49.6, 20.7),('Jackson Holliday', 55.6, 0.058, 55, 4.5, 44.9, 16.9)],
'SEA':[('Cal Raleigh', 84.9, 0.077, 53, 11.9, 62.1, 24.2),('Dominic Canzone', 70.5, 0.078, 61, 8.7, 53.1, 15.0),('Mitch Garver', 67.6, 0.079, 48, 7.4, 50.1, 22.1),('Luke Raley', 67.0, 0.065, 43, 8.4, 51.8, 15.6),('Rob Refsnyder', 65.2, 0.088, 57, 6.4, 46.5, 15.4),('Julio Rodriguez', 62.8, 0.076, 45, 6.0, 55.7, 14.5),('Cole Young', 60.4, 0.075, 50, 4.7, 40.9, 22.9),('Colt Emerson', 60.5, 0.111, 52, 7.1, 41.3, 21.1),('J.P. Crawford', 60.2, 0.082, 55, 3.6, 41.4, 17.5)],
'NYM':[('Juan Soto', 79.2, 0.073, 58, 9.1, 59.4, 15.5),('Jared Young', 71.7, 0.079, 54, 9.7, 45.2, 16.4),('Carson Benge', 60.0, 0.051, 58, 5.6, 47.7, 16.1),('MJ Melendez', 59.1, 0.071, 68, 5.8, 54.3, 21.8),('Mark Vientos', 59.1, 0.052, 24, 7.3, 54.0, 15.5),('Francisco Alvarez', 58.5, 0.037, 53, 6.8, 52.8, 13.9),('Brett Baty', 58.2, 0.092, 43, 6.0, 49.0, 13.0),('Bo Bichette', 56.3, 0.056, 50, 4.2, 54.9, 16.2),('Marcus Semien', 55.7, 0.056, 61, 5.3, 42.1, 19.8)],
'PHI':[('Kyle Schwarber', 62.3, 0.096, 64, 13.0, 70.3, 19.2),('Bryson Stott', 45.6, 0.093, 36, 3.4, 37.5, 20.3),('J.T. Realmuto', 42.7, 0.056, 37, 5.7, 54.1, 16.2),('Alec Bohm', 41.9, 0.049, 44, 3.1, 47.6, 17.0),('Gabriel Rincones', 42.6, 0.01, None, 16.2, 92.2, 17.8),('Jose Alvarado', 41.2, 0.5, None, 0.0, 0.0, 0.0),('Brandon Marsh', 41.5, 0.09, 47, 4.9, 51.4, 16.1),('Bryce Harper', 41.7, 0.124, 57, 7.5, 55.5, 16.2),('Rafael Marchan', 39.6, 0.106, 57, 3.3, 30.2, 17.8)],
'CWS':[('Colson Montgomery', 57.5, 0.04, 53, 10.2, 59.7, 20.3),('Miguel Vargas', 53.7, 0.063, 60, 5.9, 44.4, 24.7),('Sam Antonacci', 53.3, 0.047, 53, 5.2, 40.0, 16.7),('Randal Grichuk', 53.1, 0.086, 35, 6.0, 56.4, 17.5),('Jacob Gonzalez', 50.8, 0.006, 55, 3.4, 54.8, 22.8),('Andrew Benintendi', 48.1, 0.045, 48, 5.6, 39.8, 21.3),('Braden Montgomery', 46.2, 0.148, 50, 0.0, 64.3, 14.0),('Chase Meidroth', 42.7, 0.075, 49, 1.3, 40.9, 13.6),('Tristan Peters', 43.2, 0.063, 54, 3.7, 39.8, 17.7)],
'NYY':[('Ben Rice', 74.3, 0.039, 43, 11.2, 61.0, 15.3),('Paul Goldschmidt', 60.6, 0.088, 48, 5.9, 56.3, 20.2),('Jazz Chisholm', 58.6, 0.041, 53, 8.8, 49.9, 14.8),('Cody Bellinger', 53.7, 0.068, 27, 5.2, 41.6, 20.6),('Ryan McMahon', 53.7, 0.033, 53, 5.5, 53.2, 18.1),('Anthony Volpe', 50.7, 0.077, 33, 3.7, 46.8, 17.4),('Jasson Dominguez', 50.5, 0.04, 45, 4.8, 60.8, 14.6),('J.C. Escarra', 50.3, 0.043, 38, 5.0, 45.9, 14.0),('Spencer Jones', 48.3, 0.058, 53, 3.2, 75.3, 25.4)],
'SF':[('Rafael Devers', 76.3, 0.123, 56, 7.5, 60.7, 20.4),('Bryce Eldridge', 72.4, 0.025, 53, 5.8, 63.5, 18.4),('Matt Chapman', 71.9, 0.066, 57, 6.5, 55.2, 22.1),('Willy Adames', 70.7, 0.068, 47, 6.7, 47.6, 19.7),('Victor Bericoto', 70.0, 0.033, 41, 5.6, 64.1, 10.1),('Casey Schmitt', 68.1, 0.086, 52, 6.6, 48.4, 20.7),('Adrian Houser', 68.1, 0.5, None, 0.0, 31.2, 13.6),('Logan Webb', 65.1, 0.5, None, 3.3, 25.0, 11.6),('Eric Haase', 61.8, 0.037, 49, 6.6, 42.8, 15.8)],
'ATL':[('Matt Olson', 82.4, 0.079, 57, 8.3, 62.4, 22.4),('Drake Baldwin', 79.3, 0.086, 67, 7.8, 57.5, 16.2),('Austin Riley', 78.6, 0.062, 41, 9.1, 56.5, 19.0),('Rowdy Tellez', 71.9, 0.041, None, 7.3, 48.0, 20.4),('Mike Yastrzemski', 70.9, 0.074, 40, 6.3, 49.5, 22.0),('Michael Harris', 66.1, 0.087, 48, 6.1, 53.2, 13.1),('Ha-Seong Kim', 61.5, 0.075, 38, 3.5, 38.2, 20.0),('Dominic Smith', 60.9, 0.077, 43, 4.2, 40.2, 17.0),('Ozzie Albies', 60.7, 0.147, 49, 4.5, 40.3, 19.6)],
'STL':[('Lars Nootbaar', 64.6, 0.065, 51, 6.6, 50.6, 16.3),('Nelson Velazquez', 64.1, 0.071, 57, 9.4, 47.5, 16.6),('Ivan Herrera', 62.0, 0.062, 47, 5.9, 55.4, 12.1),('JJ Wetherholt', 61.4, 0.053, 39, 5.6, 50.7, 21.5),('Alec Burleson', 58.2, 0.075, 63, 4.7, 48.9, 16.3),('Jordan Walker', 54.6, 0.053, 50, 6.5, 54.3, 13.7),('Jimmy Crooks', 53.3, 0.013, 51, 0.0, 42.7, 20.6),('Nathan Church', 50.6, 0.054, 28, 4.4, 38.0, 20.6),('Masyn Winn', 48.7, 0.101, 65, 2.8, 39.3, 20.0)],
'KC':[('Bobby Witt', 68.4, 0.091, 60, 7.1, 51.5, 22.8),('Nick Loftin', 60.1, 0.085, 50, 3.3, 36.2, 13.9),('Maikel Garcia', 59.2, 0.057, 41, 2.9, 48.2, 14.8),('Lane Thomas', 59.7, 0.062, 56, 5.6, 44.4, 19.3),('Jac Caglianone', 60.5, 0.028, 53, 8.1, 61.9, 11.4),('John Rave', 57.9, 0.021, None, 2.4, 46.8, 13.1),('Michael Massey', 57.9, 0.085, 64, 5.3, 46.2, 20.6),('Salvador Perez', 56.0, 0.107, 41, 8.1, 54.0, 19.8),('Isaac Collins', 53.6, 0.045, 60, 4.2, 42.6, 19.3)],
'LAA':[('Mike Trout', 74.1, 0.113, 60, 11.4, 55.3, 22.9),('Jo Adell', 54.1, 0.114, 47, 7.6, 54.5, 20.0),('Reid Detmers', 51.8, 0.5, None, 0.0, 0.0, 20.0),('Zach Neto', 51.1, 0.098, 48, 8.2, 50.9, 15.9),("Logan O'Hoppe", 50.5, 0.128, 66, 7.4, 53.9, 17.7),('Donovan Walton', 47.0, 0.057, 44, 5.7, 35.5, 16.7),('Nolan Schanuel', 45.9, 0.086, 44, 2.6, 31.9, 14.5),('Vaughn Grissom', 44.4, 0.138, 68, 2.9, 42.2, 14.3),('Jose Siri', 44.1, 0.181, 54, 8.9, 43.9, 17.9)],
'ATH':[('Nick Kurtz', 90.6, 0.5, 53, 8.6, 65.6, 17.9),('Shea Langeliers', 82.1, 0.5, 55, 8.2, 52.0, 21.4),('Max Muncy (ATH)', 75.2, 0.5, 48, 7.0, 50.8, 14.7),('Tyler Soderstrom', 74.5, 0.5, 32, 6.4, 51.8, 15.4),('Colby Thomas', 74.4, 0.5, 50, 8.4, 50.6, 26.1),('Carlos Cortes', 71.7, 0.5, 38, 6.0, 44.1, 16.7),('Lawrence Butler', 68.7, 0.5, 54, 5.1, 48.7, 16.1),('Zack Gelof', 66.4, 0.5, 59, 4.8, 45.6, 15.3),('Jonah Heim', 64.2, 0.5, 65, 4.2, 42.8, 20.4)]
}
# ---- lineup status ----
# A bat is 'confirmed' ONLY when a posted lineup (slate_auto 'lu') actually contains it.
# Until that team's card posts, everyone on it is 'projected' (never blanket-confirmed).
# SCRATCHED is an optional same-day hand list for known scratches BEFORE lineups post
# (injury/rest); leave it empty otherwise — it must be re-curated each slate, never reused.
SCRATCHED=[]                              # e.g. ["Some Hitter"] for a known same-day scratch
OUTN={norm(x) for x in SCRATCHED}
def _is_late(gt):
    try:
        hm,ap=gt.split(); h,m=map(int,hm.split(':')); h=(h%12)+(12 if ap.upper()=='PM' else 0); return h*60+m>=21*60
    except Exception: return False
players={}
for (gm,gn,gt,wf,away,home,asp,hsp) in GAMES:
    _sl=SLATE.get(gm,{})
    if _sl.get('wf') is not None: wf=_sl['wf']            # auto-pulled park/weather wins
    for code,oppSP in ((away,hsp),(home,asp)):   # away hitters face home SP, vice versa
        opp_name,opp_hand,opp_hr9=oppSP
        opp_hr9=_sl.get('sp',{}).get(norm(opp_name),opp_hr9)  # auto-pulled HR/9 wins
        for (nm,aT,z,form,pb,hh,la) in ROWS[code]:
            key=nm; n=norm(nm)
            iso=ISO.get(n); iso_used=iso if iso is not None else ISO_FLOOR
            powraw=pb*hh*la_window(la); lean='Boost' if wf>1.02 else ('Suppress' if wf<0.98 else 'Neutral')
            _lu=_sl.get('lu',{}).get(code)              # posted lineup for this team (None until it posts)
            if _lu:                                      # card POSTED -> in/out from the lineup; 'confirmed' ONLY if it's the official (not projected) lineup
                _in=(n in _lu); _out=(not _in)
                _status=('confirmed' if code in _sl.get('conf',set()) else 'projected') if _in else 'projected'
            else:                                        # card NOT posted yet -> projected; only explicit hand-scratches sit out
                _status='projected'; _out=(n in OUTN)
            players[key]=dict(nm=key,code=code,team=FULL[code],aT=aT,zonev=z,form=form,pb=pb,hh=hh,la=la,
                iso=(f".{str(iso).split('.')[1]}" if iso is not None else '\u2014'),iso_used=iso_used,powraw=powraw,
                hr9=opp_hr9,wf=wf,game=gn,gmatch=gm,gtime=gt,late=_is_late(gt),rain=False,out=_out,status=_status,
                opp=[opp_name,opp_hand],oppERA=None,ftrend=FT.get(n,'flat'),odds=ODDS.get(n),soft=(opp_hr9 is None),why=f"{gm.replace('@',' @ ')} ({lean}). Faces {opp_name} ({opp_hand}).")
# ---- percentile/median normalization across the FULL in-lineup pool ----
pool=list(players.values()); raws=sorted(r['powraw'] for r in pool); N=len(raws)
def pct(p): i=p/100*(N-1); lo=int(i); hi=min(lo+1,N-1); return raws[lo]+(raws[hi]-raws[lo])*(i-lo)
p5,p95=pct(5),pct(95)
for r in pool: r['powidx']=round(clamp(100*(r['powraw']-p5)/(p95-p5),0,100)) if p95>p5 else 50
medP=st.median([r['powidx'] for r in pool]); medI=st.median([r['iso_used'] for r in pool])
zs=[r['zonev'] for r in pool if abs(r['zonev']-0.5)>1e-9]; medZ=st.median(zs)
powT=lambda P:clamp(1+0.15*(P-medP)/40,0.85,1.15)
isoT=lambda I:clamp(1+0.08*(I-medI)/0.06,0.92,1.08)
zoneT=lambda z:1.0 if abs(z-0.5)<1e-9 else clamp(1+0.05*(z-medZ)/0.05,0.95,1.05)
for r in pool:
    r['TOTAL']=round(r['aT']*powT(r['powidx'])*isoT(r['iso_used'])*zoneT(r['zonev'])*fF(r['form'])*mM(r['hr9'])*pM(r['wf']),1)

# ---- rich per-player why blurbs (restored copy generator from 2026-06-17 build) ----
def _isostr(p):
    iso = p.get('iso')
    return iso if (iso and iso != '\u2014') else None


def why(p):
    nm = p['nm']; pw = p.get('powidx', 0) or 0; hh = p.get('hh', 0) or 0; la = p.get('la', 0) or 0
    hr9 = p.get('hr9'); wf = p.get('wf', 1.0); opp = (p.get('opp') or ['the starter'])[0]
    # power tier
    if pw >= 80:
        s = f"{nm} is one of the slate's loudest bats \u2014 a {pw:.0f}/100 power grade with {hh:.0f}% of contact hit hard."
    elif pw >= 58:
        s = f"{nm} carries real pop \u2014 {pw:.0f}/100 power and {hh:.0f}% hard contact."
    elif pw >= 40:
        s = f"{nm} grades mid-tier for power ({pw:.0f}/100), {hh:.0f}% hard contact \u2014 more ceiling than floor."
    else:
        s = f"{nm} is a contact-first bat ({pw:.0f}/100 power), squarely a longshot dart."
    # launch
    if la >= 14 and la <= 26:
        s += f" His {la:.0f}\u00b0 average launch sits right in the home-run window."
    elif la < 14:
        s += f" The {la:.0f}\u00b0 launch runs a bit flat, so he has to get under one."
    else:
        s += f" A steep {la:.0f}\u00b0 stroke \u2014 he needs to stay through it."
    # iso
    iso = _isostr(p)
    if iso and float('0' + iso) >= 0.20:
        s += f" That {iso} ISO is real extra-base juice."
    # matchup
    if hr9 is None:
        s += f" {opp} is the matchup."
    elif hr9 >= 1.5:
        s += f" {opp} ({hr9:.2f} HR/9) has been homer-prone \u2014 that's the draw."
    else:
        s += f" {opp} ({hr9:.2f} HR/9) is a tougher assignment, though."
    # park
    if wf is not None and wf > 1.02:
        s += " The yard's playing as a launch pad tonight."
    elif wf is not None and wf < 0.98:
        s += " The park's knocking balls down tonight."
    s += f" Model lands him at {p.get('TOTAL', 0):.0f}."
    return s

for r in pool: r['why'] = why(r)
wx={}
WXEMО={'TOR@BOS': ('☀️', 'wind out 21mph, 75°'), 'CLE@MIL': ('🏟', 'Dome'), 'MIN@TEX': ('🏟', 'Dome'), 'BAL@SEA': ('🏟', 'Dome'), 'NYM@PHI': ('☀️', 'wind out 17mph, 89°'), 'CWS@NYY': ('☀️', 'wind out 16mph, 88°'), 'SF@ATL': ('🌧️', 'wind out 10mph, 75°, rain'), 'STL@KC': ('⛅', 'L-R 6mph, 78°'), 'LAA@ATH': ('⛅', 'wind 13mph, 82°, Sacramento')}
for (gm,gn,gt,wf,away,home,asp,hsp) in GAMES:
    em,cond=WXEMО[gm]; lean='Boost' if wf>1.02 else ('Suppress' if wf<0.98 else 'Neutral')
    _sl=SLATE.get(gm,{}); _w=_sl.get('weather',{}); _wf=_sl['wf'] if _sl.get('wf') is not None else wf
    lean=_w.get('lean') or ('Boost' if _wf>1.02 else ('Suppress' if _wf<0.98 else 'Neutral'))
    wx[str(gn)]={'emoji':_w.get('emoji',em),'lean':lean,'factor':_wf,'park':gm,
        'cond':_w.get('cond',cond),'rain':(f"{_w.get('precip')}% rain" if _w.get('precip') is not None else '0% rain'),'precip':(_w.get('precip') if _w.get('precip') is not None else 0)}
# ---- season ledger: carry forward prior state + fold the last graded night ----
# Paths/dates are env-overridable; if the carryover files aren't present (e.g. CI),
# carry a committed season if available, else start a neutral ledger. No day-specific assert.
# ---- season ledger ----
# season.json is the AUTHORITATIVE cumulative ledger. grade_night.py advances it each night
# (grades the prior dated board against StatsAPI results and folds it in, idempotently). build15
# just loads it. An explicit env-driven fold stays available for manual backfills only.
season=None
_pd, _nl, _nd = os.environ.get('PRIOR_D'), os.environ.get('NIGHT_LOG'), os.environ.get('NIGHT_DATE')
if _pd and _nl and _nd and os.path.exists(_pd) and os.path.exists(_nl):
    try:
        prior=json.load(open(_pd))['meta']['season']
        night=json.load(open(_nl))['nights'][_nd]['tickets']
        cats={k:dict(v) for k,v in prior['cats'].items()}
        for t in night:
            c=cats.setdefault(t['kind'],{'graded':0,'won':0,'units':0.0,'staked':0.0})
            c['graded']+=1; c['won']+=1 if t['won'] else 0
            c['units']=round(c['units']+t['net'],2); c['staked']=round(c['staked']+t['stake'],2)
        hist=list(prior['history']); run=hist[-1]
        for t in night:
            run=round(run+t['net'],2); hist.append(run)
        season={'since':prior['since'],'stake':prior['stake'],'cats':cats,'history':hist,
                'graded_nights':sorted(set(prior.get('graded_nights',[]))|{_nd})}
        print(f"season folded {_nd}: {round(sum(c['units'] for c in cats.values()),2):+.2f}u")
    except Exception as e:
        print(f"  (explicit fold failed [{e}]; falling back to season.json)")
if season is None:
    try:
        season=json.load(open(os.environ.get('SEASON_JSON','season.json')))
        print(f"  (loaded season.json: {round(sum(c.get('units',0) for c in season.get('cats',{}).values()),2):+.2f}u, graded_nights={season.get('graded_nights',[])})")
    except Exception:
        season={'since':DATE,'stake':1,'cats':{},'history':[0.0],'graded_nights':[]}
        print(f"  (no season.json — starting neutral ledger)")
maxAT=round(max(r['aT'] for r in pool),1)
meta={'wx':wx,'face':{},'maxAT':maxAT,'season':season,'date':DATE}
json.dump({'players':players,'meta':meta},open('D_0615.json','w'),indent=1)
print(f"maxAT={maxAT}")
# report
print(f"FULL POOL = {len(players)} in-lineup hitters | medians POWER{medP:.0f} ISO{medI:.3f} Zone{medZ:.3f} | p5={p5:.0f} p95={p95:.0f}")
priced=sorted([r for r in pool if r['odds']],key=lambda r:-(100/(r['odds']+100)))[:33]
priced.sort(key=lambda r:-r['TOTAL'])
print(f"\nBETTING POOL (top-33 by implied), re-ranked by full-pool TOTAL:")
print(f"{'#':>2} {'TOTAL':>6} {'aT':>5} {'PWR':>3} {'mM':>4} player (team)")
for i,r in enumerate(priced,1):
    print(f"{i:>2} {r['TOTAL']:6.1f} {r['aT']:5.1f} {r['powidx']:3d} {mM(r['hr9']):4.2f} {r['nm']} ({r['code']})")
print("\nFULL-POOL TOP 12 (incl. non-bet bats):")
for r in sorted(pool,key=lambda r:-r['TOTAL'])[:12]:
    tag='' if r['odds'] else '  (no market)'
    print(f"  {r['TOTAL']:6.1f}  {r['nm']} ({r['code']}){tag}")
