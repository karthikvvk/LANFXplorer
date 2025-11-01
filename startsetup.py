import os

dirs = os.listdir()


lis = ['.env', '1_Select_Host.py',  'server.py', 'requirement.txtt', 'scanner.py', 'startsetup.py', 'pages/2_File_Manager.py', 'set_static_ip.py']
for i in lis:
    if i in dirs:
        pass
    else:
        print("Critical Files are not Available!!")


cdir = os.getcwd()
os.system("python " + cdir + "/set_static_ip.py")