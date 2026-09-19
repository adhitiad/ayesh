import base64
c = base64.b64decode(open(r'E:\code\fr\chat_b64.txt', 'rb').read())
with open(r'E:\code\fr\src\api\routes_chat.py', 'wb') as f:
    f.write(c)
print('done')
