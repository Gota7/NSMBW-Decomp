#include <types.h>
#include <dol/cLib/c_math.hpp>
#include <lib/msl_c/math.h>

// This is absolutely terrible but I can't fix the regalloc.
inline int cM::rad2i(float radians)
{
#ifdef NON_MATCHING
    return (int)(10430.378f * fmod(radians, 6.2831854820251465)); // Making sure we check where we are around the circumference of the circle.
#else
    register float remainder = fmod(radians, 6.2831854820251465);
    register float multiplier = 10430.378f;
    asm(fmuls multiplier, remainder, multiplier);
    return (int)multiplier;
#endif
}

s16 cM::rad2s(float radians)
{
    int converted = rad2i(radians);
    if (converted < -0x8000)
    {
        converted += 0x10000;
    }
    else if (converted > 0x7FFF)
    {
        converted -= 0x10000;
    }
    return (s16)converted;
}