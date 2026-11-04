# Abrir Gaveta PDV

Abre a gaveta de dinheiro ligada a uma impressora térmica (ESC/POS, padrão EPSON/ELGIN) no Windows, com um clique, sem imprimir cupom e sem janela de console.

Gratuito, de código aberto (licença MIT) e sem coleta de dados. Veja a [Política de Privacidade](PRIVACY.md).

## Instalar

Pela **Microsoft Store**: busque por "Abrir Gaveta PDV". A Store faz a instalação e as atualizações.

## Como usar

| Ação | O que acontece |
|---|---|
| Abrir o programa | Abre a gaveta |
| Abrir segurando **Shift** | Abre o menu de configurações |
| Primeira execução | Abre o menu de configurações sozinho |
| Tecla de atalho (se ativada) | Abre a gaveta de qualquer tela |

Se a gaveta falhar, o programa pergunta se você quer alterar as configurações.

### Menu de configurações

1. **Impressora:** escolha a impressora ligada à gaveta (ou digite o nome exato).
2. **Código de abertura:** o padrão é `1B 70 00 19 FA` (ESC p 0 25 250) e nunca é apagado. Marque **Editar código (avançado)** para usar outro código em hexadecimal. Ao desmarcar, o padrão volta.
3. **Tecla de atalho:** marque **Abrir a gaveta com uma tecla de atalho**, escolha os modificadores (Ctrl, Alt, Shift, Win) e a tecla. Exemplo: `Ctrl+Alt+Space`.
4. **Iniciar junto com o Windows:** o botão abre Configurações > Aplicativos > Inicialização, onde você ativa "Abrir Gaveta PDV".
5. **Testar gaveta:** envia o código com os valores da tela, sem salvar.

Com a tecla de atalho ativa, o programa fica em segundo plano, com um ícone perto do relógio. Clique com o botão direito no ícone para **Abrir gaveta**, **Configurações** ou **Sair**. Se o atalho for desligado, o programa em segundo plano fecha sozinho.

As configurações ficam em `%LOCALAPPDATA%\Gaveta\gaveta.config`.

## Compilar

Requer Windows, Python 3 e o [Windows SDK](https://developer.microsoft.com/windows/downloads/windows-sdk/) (traz o `makeappx.exe`).

```bash
compilar.bat
empacotar_msix.bat
```

1. `compilar.bat` gera o programa em `Store\abrir_gaveta\` (inclui o `gaveta_inicio.exe`, usado para iniciar com o Windows).
2. `empacotar_msix.bat` gera o `Abrir_Gaveta_PDV.msix`, que é enviado ao Partner Center.

O pacote não é assinado: a Microsoft assina na certificação. Para testar sem empacotar: `python abrir_gaveta.py` (ou `python abrir_gaveta.py --configurar`).

O manifesto está em `msix/AppxManifest.xml`. A cada nova versão enviada à Store, aumente o número em `Version` (o último dígito deve ficar 0).

O GitHub Actions (`.github/workflows/build.yml`) gera o `.msix` a cada push.

## Estrutura

```text
abrir_gaveta.py        Programa (abrir gaveta + configurações)
compilar.bat           Compila o programa
empacotar_msix.bat     Gera o .msix para a Microsoft Store
msix/                  Manifesto e logos do pacote
.github/workflows/     Compilação automática
PRIVACY.md             Política de privacidade
LICENSE                Licença MIT
```

## Licença

[MIT](LICENSE) © 2026 MelusDev
