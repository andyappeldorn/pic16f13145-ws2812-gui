#include "led_protocol.h"
#include "mcc_generated_files/uart/eusart1.h"
#include "mcc_generated_files/spi/mssp1.h"
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

led_color_t leds[NUMBER_OF_LEDS];
uint8_t led_mode = LED_MODE_RGB;

static uint8_t cmd_buffer[64];
static uint8_t cmd_index = 0;

static void uart_put_char(char c)
{
    while (!EUSART1_IsTxReady())
        ;
    EUSART1_Write((uint8_t)c);
}

static void uart_put_string(const char *s)
{
    while (*s != '\0')
        uart_put_char(*s++);
    while (!EUSART1_IsTxDone())
        ;
}

static uint8_t parse_uint8(const char *str)
{
    uint16_t val = atoi(str);
    if (val > 255)
        val = 255;
    return (uint8_t)val;
}

static void tokenize_and_execute(void)
{
    char *tokens[5];
    uint8_t token_count = 0;

    cmd_buffer[cmd_index] = '\0';

    char *copy = (char *)cmd_buffer;

    while (*copy && token_count < 5)
    {
        while (*copy && (isspace(*copy)))
            copy++;

        if (*copy == '\0')
            break;

        tokens[token_count] = copy;
        token_count++;

        while (*copy && !isspace(*copy))
            copy++;

        if (*copy)
            *copy++ = '\0';
    }

    if (token_count == 0)
        return;

    char cmd = tokens[0][0];

    switch (cmd)
    {
        case 'L':
        case 'l':
            if (token_count >= 4)
            {
                uint8_t led_num = parse_uint8(tokens[0] + 1);
                if (led_num >= NUMBER_OF_LEDS)
                    break;

                leds[led_num].red   = parse_uint8(tokens[1]);
                leds[led_num].green = parse_uint8(tokens[2]);
                leds[led_num].blue  = parse_uint8(tokens[3]);
                leds[led_num].white = (token_count >= 5) ? parse_uint8(tokens[4]) : 0;

                LED_Protocol_UpdateLEDs();
            }
            break;

        case 'A':
        case 'a':
            if (token_count >= 4)
            {
                uint8_t r = parse_uint8(tokens[1]);
                uint8_t g = parse_uint8(tokens[2]);
                uint8_t b = parse_uint8(tokens[3]);
                uint8_t w = (token_count >= 5) ? parse_uint8(tokens[4]) : 0;

                for (uint8_t i = 0; i < NUMBER_OF_LEDS; i++)
                {
                    leds[i].red   = r;
                    leds[i].green = g;
                    leds[i].blue  = b;
                    leds[i].white = w;
                }

                LED_Protocol_UpdateLEDs();
            }
            break;

        case 'C':
        case 'c':
            for (uint8_t i = 0; i < NUMBER_OF_LEDS; i++)
            {
                leds[i].green = 0;
                leds[i].red   = 0;
                leds[i].blue  = 0;
                leds[i].white = 0;
            }
            LED_Protocol_UpdateLEDs();
            break;

        case 'U':
        case 'u':
            LED_Protocol_UpdateLEDs();
            break;

        case 'M':
        case 'm':
            if (token_count >= 2)
            {
                uint8_t mode = parse_uint8(tokens[1]);
                if (mode == LED_MODE_RGB || mode == LED_MODE_RGBW)
                {
                    led_mode = mode;
                }
            }
            break;

        default:
            break;
    }
}

void LED_Protocol_Init(void)
{
    cmd_index = 0;
    memset(cmd_buffer, 0, sizeof(cmd_buffer));
}

void LED_Protocol_ProcessRxData(void)
{
    while (EUSART1_IsRxReady())
    {
        uint8_t ch = EUSART1_Read();

        uart_put_char((char)ch);

        if (ch == '\n' || ch == '\r')
        {
            if (cmd_index > 0)
            {
                tokenize_and_execute();
                cmd_index = 0;
            }
        }
        else if (cmd_index < (sizeof(cmd_buffer) - 1))
        {
            cmd_buffer[cmd_index++] = ch;
        }
    }
}

void LED_Protocol_UpdateLEDs(void)
{
    SPI1_Open(MSSP1_DEFAULT);
    for (uint8_t i = 0; i < NUMBER_OF_LEDS; i++)
    {
        SPI1_ByteExchange(leds[i].green);
        SPI1_ByteExchange(leds[i].red);
        SPI1_ByteExchange(leds[i].blue);
        if (led_mode == LED_MODE_RGBW)
        {
            SPI1_ByteExchange(leds[i].white);
        }
    }
    SPI1_Close();
}

void LED_Protocol_PrintStartupBanner(void)
{
    uart_put_string(
        "\r\n"
        "WS2812 UART demo ready.\r\n"
        "\r\n"
        "Commands (terminate each line with Enter):\r\n"
        "  L<n> R G B [W]  Set LED n RGB or RGBW\r\n"
        "  A R G B [W]     Set all LEDs\r\n"
        "  C               Clear all (off)\r\n"
        "  U               Push buffer to strip\r\n"
        "  M <3|4>         Set mode: 3=RGB, 4=RGBW\r\n"
        "\r\n");
}
