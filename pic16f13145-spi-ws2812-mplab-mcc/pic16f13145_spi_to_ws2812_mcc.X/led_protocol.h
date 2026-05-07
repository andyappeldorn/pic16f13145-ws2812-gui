#ifndef LED_PROTOCOL_H
#define LED_PROTOCOL_H

#include <stdint.h>

typedef struct
{
    uint8_t green;
    uint8_t red;
    uint8_t blue;
    uint8_t white;
} led_color_t;

#define NUMBER_OF_LEDS      8

#define LED_MODE_RGB        3
#define LED_MODE_RGBW       4

extern led_color_t leds[NUMBER_OF_LEDS];
extern uint8_t led_mode;

void LED_Protocol_Init(void);
void LED_Protocol_ProcessRxData(void);
void LED_Protocol_UpdateLEDs(void);
void LED_Protocol_PrintStartupBanner(void);

#endif
