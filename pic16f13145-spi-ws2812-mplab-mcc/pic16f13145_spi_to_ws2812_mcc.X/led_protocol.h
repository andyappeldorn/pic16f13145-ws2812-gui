#ifndef LED_PROTOCOL_H
#define LED_PROTOCOL_H

#include <stdint.h>

typedef struct
{
    uint8_t green;
    uint8_t red;
    uint8_t blue;
} rgb_t;

#define NUMBER_OF_LEDS  8
#define RGB_SIZE        (NUMBER_OF_LEDS * 3)

extern rgb_t leds[NUMBER_OF_LEDS];

void LED_Protocol_Init(void);
void LED_Protocol_ProcessRxData(void);
void LED_Protocol_UpdateLEDs(void);
void LED_Protocol_PrintStartupBanner(void);

#endif
