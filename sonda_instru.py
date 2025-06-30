import math
import digi
from tkinter import *
from tkinter import messagebox
from tkinter import filedialog
from datetime import datetime
from datetime import timedelta
import time
from collections import deque
#import graficas

class sondaError(Exception):
    pass

class noOkError(sondaError):
    '''
    la sonda no responde OK
    '''

class sonda(digi.digi):
    '''clase de sonda cautiva'''
    def __init__(self,*arg,**kw):
        digi.digi.__init__(self,*arg,**kw)
        #inicialización de propiedades
        self.dirS=None
        self.iSample= None
        self.iSave=None
        self.fhora=None
        self.sinc=None
        self.compass_cal=False
        self.terminar=False
        self.cte_viento=17.0
        self.inicio_datos=64
        self.avance_datos=0
        return None

    def comp2v(self,x,y):
        '''convierte de componentes de viento a vector'''
        if x>=128:
            x-=256
        if y>=128:
            y-=256
        try:
            heading=math.degrees(math.atan(y/x))
            if x>0 and y>0:
                heading=360-heading
            if x>0 and y<0:
                heading=-heading
            if x<0:
                heading=180-heading
        except ZeroDivisionError:
            if y<0:
                heading=90
            else:
                heading=270
        #print('c=',x,y,int(heading),(((x**2)+(y**2))**0.5)/60)
        return heading    

    def leepaq(self,maxbytes=14):
        '''lee un paquete de datos verificando el checksum'''
        ans=self.readbytes(maxbytes)
        lenpq=len(ans)
        #if lenpq!=0:
            #print(list(ans),lenpq)
        chk=None
        if lenpq>=3:
            ansLs=list(ans[0:-2])
            chk2=0
            for b in ansLs:
                chk2=chk2+b
            chk2=chk2&0xffff
            chk=int.from_bytes(ans[lenpq-2:lenpq],'big')
            #print(chk,chk2)
            if chk==chk2 and chk!=0:
                return ans,lenpq
            else:
                return None,lenpq
        return None,lenpq

    def to_altura(self,altura_base, presion):
        '''
        calcula la altura con respecto a una altura base
        '''
        h=11901.771*(pow(altura_base,0.19)-pow(presion,0.19))
        return h
    
    def to_temp(self,temp_h,temp_l):
        '''
        convierte de datos crudos a temperatura
        '''
        t=((temp_h<<8)+temp_l)*0.04-39.6
        return t
      
    def to_HR(self,humedad,temp):
        '''
        convierte de datos crudos a HR,
        compensa con temperatura
        '''
        HR=-4+0.648*humedad-.00072*(humedad**2)
        #compensando humedad con temperatura
        HR+=(temp-25)*(0.01+0.00128*humedad)
        return HR
    
    def to_WD(self,wd_raw,sign):
        '''
        convierte a dirección de viento,
        se requiere el byte con el signo
        '''
        if wd_raw>90:
            wd_raw-=256
        if (sign>>7):
            wd_raw+=180
        if wd_raw<0:
            wd_raw+=360
        return wd_raw
    
    def to_O3(self,o3):
        return o3*1.23
    
    def fDatos(self,datosraw):
        '''formatea los datos para sonda'''
        if datosraw[1]==7:
            datos=[
                #0:presión
                ((datosraw[0][0]<<8)+datosraw[0][1])/10.0,
                #1:altura
                ((datosraw[0][2]<<8)+datosraw[0][3])/10.0,
                #2:viento
                round(datosraw[0][4]/self.cte_viento,1),
                #3:presion base para altura
                ((datosraw[0][2]<<8)+datosraw[0][3])/10.0,
                
                ]
            datos[1]=self.to_altura(datos[1],datos[0])
            datos[1]=round(datos[1],1)
            return datos
        elif datosraw[1]==13:
            datos=[
                #0:viento
                self.comp2v(datosraw[0][0],datosraw[0][1]),
                #1:temperatura
                self.to_temp(datosraw[0][2],datosraw[0][3]),
                #2:Humedad relativa
                self.to_HR(datosraw[0][4],25),
                #3:memoria
                100*((datosraw[0][5]<<8)+datosraw[0][6])/65534,
                #4:analógico0
                #7+(datosraw[0][6]*-0.0265),
                datosraw[0][7],
                #5:analógico1
                self.to_O3(datosraw[0][8]),
                #6:presión
                ((datosraw[0][9]<<8)+datosraw[0][10])/10.0,
                ]
            #compensando humedad
            datos[2]=self.to_HR(datosraw[0][4],datos[1])
            #redondeando a un decimal
            for i,ndato in enumerate(datos):
                if isinstance(ndato,float):
                    datos[i]=round(ndato,1)
            return datos
        elif datosraw[1]==21:
            datos=[
                #0:fecha
                '-/-/-',
                #1:hora
                '-:-:-',
                #2:altura
                ((datosraw[0][17]<<8)+datosraw[0][18])/10,
                #3:temperatura
                self.to_temp(datosraw[0][0]&0b111111,datosraw[0][1]),
                #4:HR
                self.to_HR(datosraw[0][2],25),
                #5:Presión
                ((datosraw[0][3]<<8)+datosraw[0][4])/10,
                #6:Dirección
                self.to_WD(datosraw[0][6],datosraw[0][0]),
                #7:Velocidad
                datosraw[0][5]/self.cte_viento,
                #8:Ozono
                self.to_O3(datosraw[0][7]),
                #9:Memoria
                (datosraw[0][8]<<8)+datosraw[0][9],
                #10:isave
                datosraw[0][16]
                ]
            #compensando humedad con temperatura
            datos[4]=self.to_HR(datosraw[0][2],datos[3])
            #redondeando a un decimal
            for i,ndato in enumerate(datos):
                if isinstance(ndato,float):
                    datos[i]=round(ndato,1)
            #calculando fecha
            fechaBase=datetime(datosraw[0][10]+2000,
                        datosraw[0][11],
                        datosraw[0][12],
                        datosraw[0][13],
                        datosraw[0][14],
                        datosraw[0][15])
            tiempo=timedelta(seconds=20+datos[10]*(datos[9]-64)/8)
            fecha=fechaBase+tiempo
            datos[0]=fecha.date()
            datos[1]=fecha.time()
            #calculando altura
            datos[2]=self.to_altura(datos[2],datos[5])
            datos[2]=round(datos[2],1)
            return datos
        else:
            return None

    def showVar(self,variables,valores,unidades,marco):
        '''crea una ventana que muestra los datos'''
        etqVar=[]
        etqVal=[]
        etqUni=[]
        mvar=Frame(marco) 
        mvar.grid()
        mval=Frame(marco)
        mval.grid(column=1,row=0) 
        muni=Frame(marco)
        muni.grid(column=2,row=0)
        i=0
        fuente=("Helvetica", 18, "bold")
        for var in variables:
            etqVar.append(Label(mvar,
                text=variables[i],
                anchor='e',
                width=10,
                font=fuente))
            etqVar[-1].grid()
            etqVal.append(Label(mval,
                text=valores[i],
                font=fuente,
                width=10))
            etqVal[-1].grid()
            etqUni.append(Label(muni,
                text=unidades[i],
                anchor='w',
                width=6,
                font=fuente))
            etqUni[-1].grid()
            i+=1
        return etqVal

    def actualiza(self,etq,valores):
        '''cambia el texto en etq'''
        i=0
        for valor in valores:
            if valor!=None:
                    etq[i].config(text=valor)
            i+=1

    def escribeFile(self,archivo,valores):
        '''
        Escribe una lista de valores en el archivo dado
        '''
        with open(archivo,'a') as f:
            for var in valores:
                f.write(str(var)+' ')
            f.write('\n')

    def hilodatos(self,ctn_i,ctn_prom,
        graf_temp,graf_hum,
        graf_tprom,graf_hprom,
        cnt_rosa,rosa,img_rosa,
        temp_vs_h,tprom_vs_h,
        hr_vs_h,hrprom_vs_h,
        cnt_t,cnt_h,
        ):
        '''
        procesa los datos recibidos por el puerto
        '''
        nombre='archivo.cca'
        f=open(nombre,'w')
        f.close()
        locmem=64
        p_base=1013.25
        puntos_prom=[
            deque(maxlen=4),
            deque(maxlen=4),
            deque(maxlen=4),
            deque(maxlen=4),
            ]
        a=[None for i in range(9)]
        while not self.terminar:
            respuesta=self.leepaq(21)
            #tbytes[0]=tbytes[0]+respuesta[1]
            if respuesta[0]!=None:
                #print(respuesta)
                fres=self.fDatos(respuesta)
                tiempo=((datetime.today()- self.fhora).total_seconds())
                if respuesta[1]==7 or respuesta[1]==13:
                    if respuesta[1]==7:
                        a=[fres[1],None,None,fres[0],
                            None,fres[2],None,None,
                            None]
                        p_base=fres[3]
                    else:
                        a=[round(self.to_altura(p_base,fres[6]),1),
                            fres[1],fres[2],fres[6],
                            fres[0],None,fres[3],
                            fres[4],fres[5],
                            ]
                    #actualiza val. instantaneos
                    self.actualiza(ctn_i,a)
                    if a[1]!=None:
                        graf_temp.punto(tiempo,a[1],'+')
                        graf_hum.punto(tiempo,a[2],'o')
                        temp_vs_h.punto(a[1],a[0],'+')
                        hr_vs_h.punto(a[2],a[0],'o')
                        cnt_rosa.itemconfig(rosa,
                            image=img_rosa[self.rosa_16(a[4] )],
                            )
                elif respuesta[1]==21:
                    #actualiza val. promedio
                    self.actualiza(ctn_prom,fres)
                    #guarda en archivo
                    if locmem<fres[9]:
                        locmem=fres[9]
                        self.escribeFile(nombre,fres[0:9])
                        #grafica datos
                        puntos_prom[0].append(tiempo)
                        puntos_prom[0].append(fres[3])
                        puntos_prom[1].append(tiempo)
                        puntos_prom[1].append(fres[4])
                        puntos_prom[2].append(fres[3])
                        puntos_prom[2].append(fres[2])
                        puntos_prom[3].append(fres[4])
                        puntos_prom[3].append(fres[2])
                        if len(puntos_prom[0])==4:
                            graf_tprom.linea(puntos_prom[0][0],
                                puntos_prom[0][1],
                                puntos_prom[0][2],
                                puntos_prom[0][3])
                        if len(puntos_prom[1])==4:
                            graf_hprom.linea(puntos_prom[1][0],
                                puntos_prom[1][1],
                                puntos_prom[1][2],
                                puntos_prom[1][3])
                            
                        if len(puntos_prom[2])==4:
                            tprom_vs_h .linea(puntos_prom[2][0],
                                puntos_prom[2][1],
                                puntos_prom[2][2],
                                puntos_prom[2][3])

                        if len(puntos_prom[3])==4:
                            hrprom_vs_h.linea(puntos_prom[3][0],
                                puntos_prom[3][1],
                                puntos_prom[3][2],
                                puntos_prom[3][3])
                        cnt_t.tag_raise('linea')
                        cnt_h.tag_raise('linea')

                        #graf_tprom.punto(tiempo,fres[3],'.')
                        #graf_hprom.punto(tiempo,fres[4],'.')
                        #hr_vs_h.punto(fres[3],fres[2],'.')
                        #hrprom_vs_h.punto(fres[4],fres[2],'.')
                        
        print('hilo')

    def envia_s_cmd(self,cmd,ans='OK'):
        '''
        envia un comando y espera su respuesta
        la respuesta por defecto es 'OK'
        '''
        self.write(cmd)
        if self.read(2)!='OK':
            raise noOkError
        return True
    
    def get_dato_mem(self,loc_mem,altura_base):
        '''
        pide el dato en la localidad indicada
        '''
        
        dir_bytes=loc_mem.to_bytes(2,byteorder='big')
        chk_bytes=(dir_bytes[0]+dir_bytes[1])&0xff
        chk_bytes=chk_bytes.to_bytes(1,byteorder='big')                        
        self.write(dir_bytes+chk_bytes)
        paq_raw=self.leepaq(10)
        if paq_raw[0]==None:
            raise noOkError
        temperatura=self.to_temp(paq_raw[0][0]&0b111111, paq_raw[0][1])
        HR=self.to_HR(paq_raw[0][2],temperatura)
        presion=((paq_raw[0][3]<<8)+paq_raw[0][4])/10
        WS=paq_raw[0][5]/self.cte_viento
        WD=self.to_WD(paq_raw[0][6],paq_raw[0][0])
        O3=self.to_O3(paq_raw[0][7])
        fecha_n=self.fhora+timedelta(seconds=(((loc_mem-\
            self.inicio_datos)/8)+1)*self.i_save)
        paquete=[
            fecha_n.date(),
            fecha_n.time(),
            self.to_altura(altura_base,presion),
            temperatura,
            HR,
            presion,
            WD,
            WS,
            O3,
            ]
        for i,ndato in enumerate(paquete):
            if isinstance(ndato,float):
                paquete[i]=round(ndato,1)
        return paquete
        
    def rec_datos(self,archivo,txt_dir,cnt):
        '''
        recibe datos de la EEPROM y los almacena en
        el archivo dado
        '''
        #regresa 0 la lectura fue correcta
        #regresa 1 si no se puede obtener la cabecera de datos
        #regresa 2 si hay error en la recepción de datos
        self.open()
        nombre=archivo
        f=open(nombre,'w')
        f.close()
        try:
            self.envia_s_cmd('gParam')
        except noOkError:
            messagebox.showinfo('Instrumentación',
                'No se ha podido establecer la comunicación,\nrevise las conexiones e intente de nuevo')
            cnt.destroy()
            return 1
        #time.sleep(0.1)
        cabecera=self.leepaq(14)
        self.close()
        self.fhora=datetime(2000+cabecera[0][2],
            cabecera[0][3],
            cabecera[0][4],
            cabecera[0][5],
            cabecera[0][6],
            cabecera[0][7]+20)
        self.i_sample=cabecera[0][0]
        self.i_save=cabecera[0][1]
        altura_base=((cabecera[0][8]<<8)+cabecera[0][9])/10
        dir_mem=(cabecera[0][10]<<8)+cabecera[0][11]
        self.open()
        t_i=time.time()
        dir_n=self.inicio_datos
        txt_dir.set(str(dir_n))
        try:
            self.envia_s_cmd('gDatos')
        except noOkError:
            messagebox.showinfo('Instrumentación',
                'Se ha perdido la comunicación,\nposiblemente no se hayan guardado todos los datos')
            cnt.destroy()
            return 2
        while dir_n<dir_mem:
            n_pack=0
            paquetes=[]
            while n_pack < 100 and dir_n<dir_mem:
                n_errores=0
                dato_ok=False
                while not dato_ok:
                    try:
                        paquetes.append(self.get_dato_mem(dir_n,
                                    altura_base))
                        dato_ok=True
                    except noOkError:
                        #print('error!',n_errores)
                        n_errores+=1
                        if n_errores>10:
                            messagebox.showinfo('Instrumentación',
                                'Se ha perdido la comunicación,\nposiblemente no se hayan guardado todos los datos')
                            cnt.destroy()
                            return 2
                dir_n+=8
                n_pack+=1
                txt_dir.set(str(dir_n))
                #quitar??
                self.avance_datos=dir_n
                #print(dir_n,paquetes)
                
            for paquete in paquetes:
                self.escribeFile(nombre,paquete)

        self.write(0xffff.to_bytes(2,'big'))
        self.close()
        print(time.time()-t_i)
        messagebox.showinfo('Instrumentación',
            'La recuperación de datos\nha terminado con éxito')
        cnt.destroy()
        return 0
        
    def pide_nombre(self,contenedor):
        '''
        ventana que pide el nombre de un archivo al usuario
        '''
        tipos=[
            ('Archivo de sonda','*.cca'),
            ('Archivos de texto','*.txt'),
            ('Archivos csv','*.csv'),
            ]
        hora=datetime.today()
        f_name=hora.strftime('%y%m%d_%H%M')+'.cca'
        nombre=filedialog.asksaveasfilename(
            defaultextension='.cca',
            filetypes=tipos,
            initialfile=f_name,
            title='Proporcione el nombre del archivo',
            parent=contenedor
            )
        return nombre
    
    def rosa_16(self,dir_v):
        i_direccion= int((dir_v+11.25)/22.5)
        if i_direccion==16:
            i_direccion=0
        return i_direccion
        